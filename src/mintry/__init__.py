import os
from contextlib import contextmanager
from typing import Iterable, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet
from mintry.core.policy_sync import PolicyCache, PolicySyncWorker
from mintry.core.control_plane import SupabaseControlPlaneClient
from mintry.core.crypto import verify_policy_bundle_signature, normalize_pem
from mintry.core.exceptions import MintryMandateExceeded
from mintry.core.notifications import BudgetWatch
from mintry.core.telemetry_batch import TelemetryBatcher
from mintry import telemetry as _telemetry

__version__ = "1.2.0"

__all__ = [
    "init",
    "close",
    "mandate",
    "MintryMandateExceeded",
    "PolicyEngine",
    "MintryWallet",
]

# ── Global state ─────────────────────────────────────────────────────
_global_engine: Optional[PolicyEngine] = None
_global_db_path: Optional[str] = None


def init(
    api_key: Optional[str] = None,
    db_path: str = "~/.mintry/vouchers.db",
    webhook_url: Optional[str] = None,
    control_plane_url: Optional[str] = None,
    control_plane_key: Optional[str] = None,
    control_plane_public_key: Optional[str] = None,
    policy_sync_interval: float = 20.0,
    default_mandate_usd: Optional[float] = None,
    budget_alert_thresholds: Optional[Iterable[float]] = None,
) -> PolicyEngine:
    """
    Initializes the Mintry Logic Fabric globally.

    Idempotent for the same resolved ``db_path``: a second call returns the
    existing engine without reinstalling hooks. Calling ``init()`` with a
    different database path closes the previous engine first.

    If ``api_key`` is not provided, falls back to the ``MINTRY_API_KEY``
    environment variable.

    Policy sync parameters (optional):
    - control_plane_url: Supabase control plane URL (MINTRY_CONTROL_PLANE_URL env var)
    - control_plane_key: Supabase API key (MINTRY_CONTROL_PLANE_KEY env var)
    - control_plane_public_key: ES256 public key for signature verification
    - policy_sync_interval: Polling interval in seconds (default: 20)

    Unattended operation (optional):
    - default_mandate_usd: cap applied to an agent that has never been budgeted,
      so a new service is governed on its first request instead of being blocked
      until someone opens the dashboard (MINTRY_DEFAULT_MANDATE_USD env var). A
      signed ``__default__`` policy rule overrides this. Unset means unknown
      agents are blocked, as before.
    - budget_alert_thresholds: utilization points that trigger a proactive notice,
      e.g. ``[0.5, 0.8, 0.95]`` (MINTRY_BUDGET_ALERT_THRESHOLDS env var).
    """
    global _global_engine, _global_db_path

    resolved_key = api_key or os.environ.get("MINTRY_API_KEY")
    if not resolved_key or not isinstance(resolved_key, str):
        raise ValueError(
            "MINTRY_API_KEY must be a non-empty string. "
            "Pass api_key= to mintry.init() or set the MINTRY_API_KEY environment variable."
        )

    from pathlib import Path

    resolved_db = str(Path(db_path).expanduser().resolve())

    # Idempotent: reuse the live engine for the same ledger path
    if _global_engine is not None and _global_db_path == resolved_db:
        if not GlobalHTTPInterceptor._installed:
            GlobalHTTPInterceptor(_global_engine).install()
        return _global_engine

    # Switching ledgers: tear down previous workers/hooks state carefully
    if _global_engine is not None:
        close()

    wallet = MintryWallet(db_path=db_path)
    engine = PolicyEngine(
        wallet,
        webhook_url=webhook_url,
        default_mandate_usd=default_mandate_usd,
    )
    engine.api_key = resolved_key
    interceptor = GlobalHTTPInterceptor(engine)

    # Proactive budget notices. Evaluated by the metering worker and delivered on
    # a background thread — never on the allow/block path.
    engine.budget_watch = BudgetWatch(
        wallet,
        thresholds=budget_alert_thresholds,
        dispatch=engine._dispatch_webhook,
    )

    # Prefer explicit arg, then documented env var
    resolved_public_key = (
        control_plane_public_key
        or os.environ.get("MINTRY_POLICY_PUBLIC_KEY")
    )
    if resolved_public_key:
        resolved_public_key = normalize_pem(resolved_public_key)
    control_plane_url = control_plane_url or os.environ.get("MINTRY_CONTROL_PLANE_URL")
    control_plane_key = control_plane_key or os.environ.get("MINTRY_CONTROL_PLANE_KEY")

    # Create signature verification function (Principle 5: Fail to last-known-good)
    def verify_bundle(bundle):
        """Verify ES256 signature on policy bundle."""
        if not resolved_public_key:
            return True  # Skip verification if no key configured (local/dev)
        try:
            return verify_policy_bundle_signature(
                {
                    "version": bundle.version,
                    "mandates": bundle.mandates,
                    "signature": bundle.signature,
                    "issued_at": bundle.issued_at,
                    "issued_by": bundle.issued_by,
                },
                resolved_public_key,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Policy signature verification failed: %s", exc)
            return False

    verify_fn = verify_bundle if resolved_public_key else None

    # Initialize policy sync worker (Principle 3: Enforce locally, always)
    # This polls for new policies from the control plane in the background
    policy_cache = PolicyCache(wallet=wallet, verify_fn=verify_fn)

    # Create control plane client for fetching policies
    control_plane = SupabaseControlPlaneClient(
        control_plane_url=control_plane_url,
        api_key=control_plane_key,
    )

    # Agent ID — primary object identifier per §9.1
    # Each deployment should set MINTRY_AGENT_ID to uniquely identify this agent
    # in the control plane. Falls back to "default_agent" for Phase 1 alpha.
    agent_id = os.environ.get("MINTRY_AGENT_ID", "default_agent")

    # Create policy sync worker
    # (Principle 4: Sync asynchronously, on a stated interval, with visible staleness)
    policy_sync_worker = PolicySyncWorker(
        policy_cache,
        fetch_fn=lambda: control_plane.fetch_policy_bundle(agent_id),
        interval_sec=policy_sync_interval,
        verify_fn=verify_fn,
    )

    # Start the background policy sync if control plane is configured
    if control_plane.url and control_plane.api_key:
        policy_sync_worker.start()

    # Attach policy infrastructure to engine
    engine.policy_cache = policy_cache
    engine.policy_sync_worker = policy_sync_worker
    engine.control_plane = control_plane
    engine.agent_id = agent_id  # expose for dashboard and telemetry

    # Inject policy cache into wallet for OPA / policy lookups
    wallet.policy_cache = policy_cache

    # Async telemetry to control plane (never on the enforcement hot path)
    telemetry_batcher = None
    if (
        control_plane.url
        and control_plane.api_key
        and os.environ.get("MINTRY_TELEMETRY_DISABLED", "").lower() not in ("1", "true", "yes")
    ):
        telemetry_batcher = TelemetryBatcher(wallet, control_plane)
        telemetry_batcher.start()
    engine.telemetry_batcher = telemetry_batcher

    # Install the global hooks
    interceptor.install()

    # Optionally start the Prometheus metrics server (MINTRY_OTEL_ENABLED=1)
    _telemetry.start_metrics_server()

    if os.environ.get("MINTRY_JSON_LOGS") != "1":
        print(f"\u2728 Mintry Logic Fabric Active | No-GIL: True")

    _global_engine = engine
    _global_db_path = resolved_db
    return engine


def close() -> None:
    """Flush wallet writes and stop background workers for the global engine."""
    global _global_engine, _global_db_path
    if _global_engine is None:
        _global_db_path = None
        GlobalHTTPInterceptor._reset()
        return
    batcher = getattr(_global_engine, "telemetry_batcher", None)
    if batcher is not None:
        batcher.stop()
    worker = getattr(_global_engine, "policy_sync_worker", None)
    if worker is not None:
        worker.stop()
    wallet = getattr(_global_engine, "wallet", None)
    if wallet is not None and hasattr(wallet, "close"):
        wallet.close()
    _global_engine = None
    _global_db_path = None
    GlobalHTTPInterceptor._reset()


def mandate(task: str, cap: float):
    """
    Top-level context manager matching the marketing ergonomics.

    Usage::

        import mintry

        mintry.init()

        with mintry.mandate("task:nightly_summarizer", cap=50.00):
            result = run_summarizer(documents)

    Wraps the internal ``engine.shield()`` logic.  If ``init()`` has not
    been called yet but ``MINTRY_API_KEY`` is set in the environment, the
    fabric auto-initializes.
    """
    global _global_engine
    if _global_engine is None:
        # Auto-initialize if the env var is available
        init()

    return _global_engine.shield(task, max_usd=cap)
