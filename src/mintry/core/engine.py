import uuid
import os
import threading
import httpx
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Any

from mintry.core.mandate_context import set_active_mandate_id, clear_active_mandate_id


def _resolve_default_cap(explicit: Optional[float]) -> Optional[float]:
    """Resolve the local fallback auto-enrollment cap.

    Returns ``None`` when unset, which keeps the historical behaviour: an unknown
    mandate has no budget and is blocked (Principle 5 — never fail open).
    """
    if explicit is not None:
        try:
            value = float(explicit)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    raw = os.environ.get("MINTRY_DEFAULT_MANDATE_USD")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


class Mandate:
    """Represents an active budget mandate for a scoped task."""

    def __init__(self, mandate_id: str, task: str, max_usd: float):
        self.id = mandate_id
        self.task = task
        self.max_usd = max_usd

    def __repr__(self):
        return f"Mandate(id={self.id!r}, task={self.task!r}, max_usd={self.max_usd})"


# Reserved key in a signed policy bundle's mandate map. Its cap applies to any
# agent the control plane has not been told about yet, which is what makes
# onboarding a new agent require no dashboard visit.
DEFAULT_MANDATE_KEY = "__default__"


class PolicyEngine:
    # Policy sync infrastructure (dynamically attached by mintry.init())
    policy_cache: Optional[Any] = None
    control_plane: Optional[Any] = None
    telemetry_batcher: Optional[Any] = None
    budget_watch: Optional[Any] = None

    def __init__(
        self,
        wallet,
        webhook_url: Optional[str] = None,
        default_mandate_usd: Optional[float] = None,
    ):
        self.wallet = wallet
        self.api_key = None
        self.webhook_url = webhook_url or os.environ.get("MINTRY_WEBHOOK_URL")
        self.default_mandate_usd = _resolve_default_cap(default_mandate_usd)

    def _record_telemetry(
        self,
        mandate_id: str,
        action: str,
        amount: float,
        details: str,
    ) -> None:
        """Queue telemetry for async control-plane upload (never blocks authorize)."""
        batcher = getattr(self, "telemetry_batcher", None)
        if batcher is None:
            return
        agent_id = getattr(self, "agent_id", None)
        batcher.record_decision(
            mandate_id,
            action,
            amount,
            details,
            agent_id=agent_id,
        )

    def _after_spend_update(self, mandate_id: str) -> None:
        """Async budget-watch evaluation after ledger spend changes."""
        watch = getattr(self, "budget_watch", None)
        if watch is None:
            return
        try:
            budget = self.effective_budget(mandate_id)
        except Exception:
            budget = None
        try:
            watch.evaluate(mandate_id, budget_usd=budget)
        except Exception:
            pass

    def _dispatch_webhook(self, payload: dict):
        """Dispatches a webhook POST request asynchronously in a background thread."""
        if not self.webhook_url:
            return
        
        def _send():
            try:
                with httpx.Client(timeout=2.0) as client:
                    client.post(self.webhook_url, json=payload)
            except Exception:
                pass
                
        threading.Thread(target=_send, daemon=True).start()

    def _policy_rule(self, mandate_id: str) -> Optional[dict]:
        """Look up a mandate's rule in the last verified local policy bundle."""
        cache = getattr(self, "policy_cache", None)
        if cache is None:
            return None
        if hasattr(cache, "mandate_rule"):
            return cache.mandate_rule(mandate_id)
        if hasattr(cache, "get_active_policy"):
            bundle = cache.get_active_policy()
            if bundle and isinstance(getattr(bundle, "mandates", None), dict):
                candidate = bundle.mandates.get(mandate_id)
                if isinstance(candidate, dict):
                    return candidate
        return None

    def default_cap(self) -> Optional[float]:
        """The cap applied to an agent no one has explicitly budgeted yet.

        A centrally signed ``__default__`` rule wins over the locally configured
        value, so the tenant sets this once in the dashboard rather than in every
        deployment's environment.
        """
        rule = self._policy_rule(DEFAULT_MANDATE_KEY)
        if isinstance(rule, dict) and "max_usd" in rule and rule.get("allow") is not False:
            try:
                value = float(rule["max_usd"])
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                return value
        return self.default_mandate_usd

    def effective_budget(self, mandate_id: str) -> float:
        """The cap in force for a mandate: signed policy first, local ledger second."""
        rule = self._policy_rule(mandate_id)
        if isinstance(rule, dict) and "max_usd" in rule:
            try:
                return float(rule["max_usd"])
            except (TypeError, ValueError):
                pass
        mandate = self.wallet.get_mandate(mandate_id)
        return float(mandate.get("budget_usd", 0.0) or 0.0)

    def authorize(self, mandate_id: str, request, deduct: bool = True):
        """
        Performs a local budget check for an outbound request.

        Uses verified PolicyCache caps when present (central governance),
        otherwise falls back to the local wallet mandate row. Spend always
        comes from the local ledger. Never performs network I/O.
        """
        mandate = self.wallet.get_mandate(mandate_id)
        spent = float(mandate.get("spent_usd", 0.0) or 0.0)
        budget = float(mandate.get("budget_usd", 0.0) or 0.0)
        status = mandate.get("status", "unknown")
        policy_expires_at = None
        policy_explicit_deny = False

        # Prefer centrally authored caps from the last verified local policy.
        rule = self._policy_rule(mandate_id)

        if rule is not None:
            if rule.get("allow") is False:
                policy_explicit_deny = True
            if "max_usd" in rule:
                budget = float(rule["max_usd"])
            policy_expires_at = rule.get("expires_at")
            if status == "unknown" and budget > 0 and not policy_explicit_deny:
                # A centrally budgeted agent that has never run on this host. Mirror
                # the signed cap into the local ledger so spend has a row to land in
                # and the ledger reports the cap actually in force.
                self._enroll(mandate_id, budget, "signed policy")
                status = "active"
        elif status == "unknown":
            # First sighting of an agent nobody budgeted. If the tenant configured
            # a default cap, enrol it locally at that cap and carry on; otherwise
            # fall through to the block below.
            enrolled = self._auto_enroll(mandate_id)
            if enrolled is not None:
                budget = enrolled
                spent = 0.0
                status = "active"

        # Phase 1: Expiry check (wallet expiry and/or policy expiry)
        expired = self.wallet.is_expired(mandate_id)
        if not expired and policy_expires_at:
            try:
                expires = datetime.fromisoformat(str(policy_expires_at).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                expired = now >= expires
            except (TypeError, ValueError):
                expired = False

        if expired:
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                "Mandate expired — request rejected"
            )
            self._record_telemetry(mandate_id, "block", 0.0, "Mandate expired — request rejected")
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "expired",
                "mandate_id": mandate_id,
                "budget_usd": budget,
                "spent_usd": spent,
            })
            return False

        if policy_explicit_deny:
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                "Blocked by central policy (allow=false)"
            )
            self._record_telemetry(mandate_id, "block", 0.0, "Blocked by central policy (allow=false)")
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "policy_deny",
                "mandate_id": mandate_id,
                "budget_usd": budget,
                "spent_usd": spent,
            })
            return False

        # Phase 2: Budget check
        if status == "exhausted":
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                f"Budget exhausted (${spent:.4f} / ${budget:.4f})"
            )
            self._record_telemetry(
                mandate_id, "block", 0.0,
                f"Budget exhausted (${spent:.4f} / ${budget:.4f})",
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "budget_exhausted",
                "mandate_id": mandate_id,
                "budget_usd": budget,
                "spent_usd": spent,
            })
            return False

        remaining = budget - spent
        if remaining < 0.01:
            self.wallet.log_decision(
                mandate_id, "block", round(remaining, 4),
                f"Insufficient headroom (${remaining:.4f} remaining)"
            )
            self._record_telemetry(
                mandate_id, "block", round(remaining, 4),
                f"Insufficient headroom (${remaining:.4f} remaining)",
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "budget_exhausted",
                "mandate_id": mandate_id,
                "budget_usd": budget,
                "spent_usd": spent,
            })
            return False

        # Reserve default headroom so concurrent requests cannot all pass.
        if not self.wallet.try_reserve(mandate_id, 0.01, budget):
            self.wallet.log_decision(
                mandate_id, "block", 0.0,
                "Insufficient headroom (concurrent reservation)"
            )
            self._record_telemetry(
                mandate_id, "block", 0.0,
                "Insufficient headroom (concurrent reservation)",
            )
            self._dispatch_webhook({
                "event": "authorization_failed",
                "reason": "budget_exhausted",
                "mandate_id": mandate_id,
                "budget_usd": budget,
                "spent_usd": spent,
            })
            return False

        # Phase 3: Apply base fee only if we aren't metering tokens post-flight
        if deduct:
            self.wallet.record_usage(mandate_id, 0.002)

        self._record_telemetry(mandate_id, "allow", 0.0, "Request authorized")
        return True

    def _enroll(self, mandate_id: str, cap: float, source: str) -> float:
        """Materialize a local mandate row at ``cap``.

        Local ledger write only — the cache is updated in-process and the row is
        persisted by the async writer, so this adds no network I/O and no blocking
        disk I/O to the request path.
        """
        self.wallet.create_mandate(mandate_id, cap)
        self.wallet.log_decision(
            mandate_id, "auto_enroll", cap,
            f"First request from this agent — enrolled at ${cap:.4f} from {source}"
        )
        self._dispatch_webhook({
            "event": "mandate_auto_enrolled",
            "mandate_id": mandate_id,
            "budget_usd": cap,
            "spent_usd": 0.0,
            "source": source,
            "headline": f"{mandate_id} started sending traffic and was capped at ${cap:,.2f}",
        })
        return cap

    def _auto_enroll(self, mandate_id: str) -> Optional[float]:
        """Enroll an unbudgeted agent at the configured default cap, if there is one."""
        cap = self.default_cap()
        if cap is None or cap <= 0:
            return None
        return self._enroll(mandate_id, cap, "the default cap")

    def get_budget_summary(self, mandate_id: str) -> dict:
        """Returns a budget summary with remaining headroom for error messages."""
        mandate = self.wallet.get_mandate(mandate_id)
        spent = float(mandate.get("spent_usd", 0.0) or 0.0)
        budget = self.effective_budget(mandate_id)
        remaining = budget - spent
        is_expired = self.wallet.is_expired(mandate_id)
        return {
            "mandate_id": mandate_id,
            "budget_usd": budget,
            "spent_usd": spent,
            "remaining_usd": round(remaining, 6),
            "status": mandate.get("status", "unknown"),
            "expired": is_expired,
        }

    @contextmanager
    def shield(
        self,
        task: str,
        max_usd: Optional[float] = None,
        expires_at: Optional[datetime] = None,
        stable_id: bool = False,
    ):
        """
        Context manager that creates or resolves a scoped mandate for a task.

        If max_usd is None, it resolves against pre-allocated dashboard mandates.
        On exit of a standard scoped mandate, marks it as exhausted.

        When stable_id=True (used by mintry.mandate()), the task name is the
        ledger mandate id and attribution is injected via ContextVar for nested LLM calls.
        """
        is_shared = False
        existing = self.wallet.get_mandate(task)

        if max_usd is not None and stable_id:
            mandate_id = task
            if existing.get("status") == "unknown":
                self.wallet.create_mandate(mandate_id, float(max_usd), expires_at=expires_at)
            else:
                self.wallet.update_mandate(
                    mandate_id, float(max_usd), expires_at=expires_at, status="active",
                )
            is_shared = True
        elif max_usd is None:
            if existing.get("status") != "unknown":
                mandate_id = task
                max_usd = existing.get("budget_usd", 0.0)
                is_shared = True
            else:
                # Auto-discovery fallback: create a default base mandate
                mandate_id = task
                max_usd = self.default_cap() or 0.05
                self.wallet.create_mandate(mandate_id, max_usd, expires_at=expires_at)
                is_shared = True
        else:
            mandate_id = f"mt_{uuid.uuid4().hex[:12]}"
            self.wallet.create_mandate(mandate_id, float(max_usd), expires_at=expires_at)

        mandate = Mandate(mandate_id=mandate_id, task=task, max_usd=float(max_usd))

        set_active_mandate_id(mandate_id)
        try:
            yield mandate
        finally:
            clear_active_mandate_id()
            if not is_shared:
                self.wallet.exhaust_mandate(mandate_id)
                mandate_info = self.wallet.get_mandate(mandate_id)
                self._dispatch_webhook({
                    "event": "mandate_exhausted",
                    "mandate_id": mandate_id,
                    "budget_usd": mandate_info.get("budget_usd", 0.0),
                    "spent_usd": mandate_info.get("spent_usd", 0.0),
                })
