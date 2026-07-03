"""Local policy cache and async sync loop for control-plane policy bundles.

Enforcement never calls into this module from the authorize hot path.
PolicyEngine reads from PolicyCache.get_active_policy() synchronously;
PolicySyncWorker updates the cache on a background polling interval.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mintry.core.wallet import MintryWallet

logger = logging.getLogger(__name__)

DEFAULT_SYNC_INTERVAL_SEC = 20
DEFAULT_CACHE_DIR = Path.home() / ".mintry" / "policy_cache"


@dataclass(frozen=True)
class PolicyBundle:
    """Signed, versioned policy payload from the control plane."""

    version: int
    mandates: dict[str, dict[str, Any]]
    signature: str
    issued_at: str
    issued_by: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyBundle":
        return cls(
            version=int(data["version"]),
            mandates=data.get("mandates", {}),
            signature=data.get("signature", ""),
            issued_at=data.get("issued_at", ""),
            issued_by=data.get("issued_by", ""),
        )


@dataclass
class PolicyCacheState:
    """Atomically-swapped in-memory policy state."""

    bundle: Optional[PolicyBundle] = None
    last_synced_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None


class PolicyCache:
    """Thread-safe last-known-good policy cache with atomic swap."""

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        wallet: Optional[MintryWallet] = None,
    ):
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._state = PolicyCacheState()
        self._wallet = wallet
        self._load_from_disk()

    @property
    def cache_file(self) -> Path:
        return self._cache_dir / "last_known_good.json"

    def _load_from_disk(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            raw = json.loads(self.cache_file.read_text())
            bundle = PolicyBundle.from_dict(raw["bundle"])
            synced = datetime.fromisoformat(raw["last_synced_at"])
            with self._lock:
                self._state = PolicyCacheState(bundle=bundle, last_synced_at=synced)
        except Exception as exc:
            logger.warning("Failed to load policy cache from disk: %s", exc)

    def get_active_policy(self) -> Optional[PolicyBundle]:
        with self._lock:
            return self._state.bundle

    def get_sync_status(self) -> dict:
        with self._lock:
            bundle = self._state.bundle
            return {
                "policy_version": bundle.version if bundle else None,
                "last_synced_at": (
                    self._state.last_synced_at.isoformat()
                    if self._state.last_synced_at
                    else None
                ),
                "last_sync_error": self._state.last_sync_error,
            }

    def get_policy_history(self, limit: int = 10) -> list[dict]:
        """Fetch policy version history from wallet (for rollback UI).

        Args:
            limit: Maximum number of versions to return (most recent first)

        Returns:
            List of policy version records.
        """
        if not self._wallet:
            return []

        try:
            conn = sqlite3.connect(self._wallet.path, isolation_level=None)
            cursor = conn.execute(
                """
                SELECT version, issued_at, issued_by, received_at, applied
                FROM policy_versions
                ORDER BY version DESC
                LIMIT ?
                """,
                (limit,),
            )
            records = [
                {
                    "version": row[0],
                    "issued_at": row[1],
                    "issued_by": row[2],
                    "received_at": row[3],
                    "applied": bool(row[4]),
                }
                for row in cursor.fetchall()
            ]
            conn.close()
            return records
        except Exception as exc:
            logger.warning("Failed to fetch policy history: %s", exc)
            return []

    def rollback_to_version(self, target_version: int) -> bool:
        """Rollback to a previous policy version (idempotent).

        Args:
            target_version: Version to roll back to

        Returns:
            True if rollback succeeded, False otherwise.
        """
        if not self._wallet:
            logger.warning("Cannot rollback: no wallet configured")
            return False

        try:
            conn = sqlite3.connect(self._wallet.path, isolation_level=None)

            # Verify target version exists
            row = conn.execute(
                "SELECT policy_json FROM policy_versions WHERE version = ?",
                (target_version,),
            ).fetchone()

            if not row:
                logger.warning("Cannot rollback: version %s not found", target_version)
                conn.close()
                return False

            policy_dict = json.loads(row[0])
            bundle = PolicyBundle(
                version=target_version,
                mandates=policy_dict,
                signature="rollback",
                issued_at=datetime.now(timezone.utc).isoformat(),
                issued_by="rollback",
            )

            # Mark other versions as not applied
            conn.execute(
                "UPDATE policy_versions SET applied = 0 WHERE version != ?",
                (target_version,),
            )

            # Apply the bundle — force=True bypasses the monotonic version guard
            # (rollback is a deliberate downgrade, not stale sync data)
            applied = self.apply_bundle(bundle, verify_fn=None, force=True)

            if applied:
                logger.info("Rolled back to policy v%s", target_version)
                # Record the rollback reason on the target version row
                conn.execute(
                    """
                    UPDATE policy_versions
                    SET rollback_reason = 'Manual rollback'
                    WHERE version = ?
                    """,
                    (target_version,),
                )

            conn.close()
            return applied

        except Exception as exc:
            logger.error("Rollback failed: %s", exc)
            return False

    def apply_bundle(
        self,
        bundle: PolicyBundle,
        *,
        verify_fn: Optional[Callable[[PolicyBundle], bool]] = None,
        force: bool = False,
    ) -> bool:
        """Verify signature and atomically swap the active policy.

        Args:
            bundle: The policy bundle to apply.
            verify_fn: Optional signature verification callable.
            force: If True, bypass the monotonic version guard. Use only for
                   deliberate rollbacks — never for background sync.
        """
        if verify_fn and not verify_fn(bundle):
            with self._lock:
                self._state.last_sync_error = "signature_verification_failed"
            logger.error(
                "Rejected unsigned/invalid policy v%s — keeping last-known-good",
                bundle.version,
            )
            return False

        with self._lock:
            current = self._state.bundle
            # Monotonic version guard: reject stale sync data, but allow forced rollbacks
            if not force and current and bundle.version <= current.version:
                return False

            now = datetime.now(timezone.utc)
            self._state = PolicyCacheState(bundle=bundle, last_synced_at=now)
            self._state.last_sync_error = None

        self._persist_to_disk(bundle, now)
        logger.info("Applied policy v%s%s", bundle.version, " (forced rollback)" if force else "")
        return True

    def _persist_to_disk(self, bundle: PolicyBundle, synced_at: datetime) -> None:
        payload = {
            "bundle": {
                "version": bundle.version,
                "mandates": bundle.mandates,
                "signature": bundle.signature,
                "issued_at": bundle.issued_at,
                "issued_by": bundle.issued_by,
            },
            "last_synced_at": synced_at.isoformat(),
        }
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.cache_file)

        # Persist to wallet's policy_versions table for versioning & rollback
        if self._wallet:
            self._persist_to_wallet(bundle, synced_at)

    def _persist_to_wallet(self, bundle: PolicyBundle, received_at: datetime) -> None:
        """Persist policy bundle to wallet's policy_versions table (append-only)."""
        try:
            # Use a direct DB connection to avoid queue batching delays
            conn = sqlite3.connect(self._wallet.path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")

            policy_json = json.dumps(bundle.mandates, separators=(",", ":"))
            # INSERT OR REPLACE so rollbacks to previously-seen versions
            # correctly update the 'applied' flag and received_at timestamp.
            # The immutable UNIQUE(version, signature) constraint is relaxed
            # here because a rollback re-applies with signature='rollback'.
            conn.execute(
                """
                INSERT OR REPLACE INTO policy_versions 
                (version, policy_json, signature, issued_at, issued_by, received_at, applied)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.version,
                    policy_json,
                    bundle.signature,
                    bundle.issued_at,
                    bundle.issued_by,
                    received_at.isoformat(),
                    True,
                ),
            )
            conn.close()
            logger.info("Persisted policy v%s to wallet", bundle.version)
        except Exception as exc:
            logger.warning("Failed to persist policy to wallet: %s", exc)


class PolicySyncWorker:
    """Background poller — fetches policy bundles from the control plane."""

    def __init__(
        self,
        cache: PolicyCache,
        fetch_fn: Callable[[], Optional[dict]],
        *,
        interval_sec: float = DEFAULT_SYNC_INTERVAL_SEC,
        verify_fn: Optional[Callable[[PolicyBundle], bool]] = None,
    ):
        self._cache = cache
        self._fetch_fn = fetch_fn
        self._interval_sec = interval_sec
        self._verify_fn = verify_fn
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mintry-policy-sync")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> bool:
        """Fetch and apply a single policy update. Returns True if applied."""
        try:
            raw = self._fetch_fn()
            if raw is None:
                return False
            bundle = PolicyBundle.from_dict(raw)
            return self._cache.apply_bundle(bundle, verify_fn=self._verify_fn)
        except Exception as exc:
            with self._cache._lock:
                self._cache._state.last_sync_error = str(exc)
            logger.warning("Policy sync poll failed: %s — enforcing last-known-good", exc)
            return False

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval_sec)
