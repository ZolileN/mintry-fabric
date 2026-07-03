import os
from contextlib import contextmanager
from typing import Optional

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
from mintry.core.crypto import verify_policy_bundle_signature
from mintry.core.exceptions import MintryMandateExceeded
from mintry import telemetry as _telemetry

__version__ = "1.0.0"

__all__ = [
    "init",
    "mandate",
    "MintryMandateExceeded",
    "PolicyEngine",
    "MintryWallet",
]

# ── Global state ─────────────────────────────────────────────────────
_global_engine: Optional[PolicyEngine] = None


def init(
    api_key: Optional[str] = None,
    db_path: str = "~/.mintry/vouchers.db",
    webhook_url: Optional[str] = None,
    control_plane_url: Optional[str] = None,
    control_plane_key: Optional[str] = None,
    control_plane_public_key: Optional[str] = None,
    policy_sync_interval: float = 20.0,
) -> PolicyEngine:
    """
    Initializes the Mintry Logic Fabric globally.

    If ``api_key`` is not provided, falls back to the ``MINTRY_API_KEY``
    environment variable.

    Policy sync parameters (optional):
    - control_plane_url: Supabase control plane URL (MINTRY_CONTROL_PLANE_URL env var)
    - control_plane_key: Supabase API key (MINTRY_CONTROL_PLANE_KEY env var)
    - control_plane_public_key: ES256 public key for signature verification
    - policy_sync_interval: Polling interval in seconds (default: 20)
    """
    global _global_engine

    resolved_key = api_key or os.environ.get("MINTRY_API_KEY")
    if not resolved_key or not isinstance(resolved_key, str):
        raise ValueError(
            "MINTRY_API_KEY must be a non-empty string. "
            "Pass api_key= to mintry.init() or set the MINTRY_API_KEY environment variable."
        )

    wallet = MintryWallet(db_path=db_path)
    engine = PolicyEngine(wallet, webhook_url=webhook_url)
    engine.api_key = resolved_key
    interceptor = GlobalHTTPInterceptor(engine)

    # Initialize policy sync worker (Principle 3: Enforce locally, always)
    # This polls for new policies from the control plane in the background
    policy_cache = PolicyCache(wallet=wallet)
    
    # Create control plane client for fetching policies
    control_plane = SupabaseControlPlaneClient(
        control_plane_url=control_plane_url,
        api_key=control_plane_key,
    )

    # Create signature verification function (Principle 5: Fail to last-known-good)
    def verify_bundle(bundle):
        """Verify ES256 signature on policy bundle."""
        if not control_plane_public_key:
            return True  # Skip verification if no key configured
        try:
            return verify_policy_bundle_signature(
                {
                    "version": bundle.version,
                    "mandates": bundle.mandates,
                    "signature": bundle.signature,
                    "issued_at": bundle.issued_at,
                    "issued_by": bundle.issued_by,
                },
                control_plane_public_key,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Policy signature verification failed: %s", exc)
            return False

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
        verify_fn=verify_bundle if control_plane_public_key else None,
    )

    # Start the background policy sync if control plane is configured
    if control_plane.url and control_plane.api_key:
        policy_sync_worker.start()

    # Attach policy infrastructure to engine
    engine.policy_cache = policy_cache
    engine.policy_sync_worker = policy_sync_worker
    engine.control_plane = control_plane
    engine.agent_id = agent_id  # expose for dashboard and telemetry

    # Inject policy cache into wallet for OPA hot-path evaluation
    wallet.policy_cache = policy_cache

    # Install the global hooks
    interceptor.install()

    # Optionally start the Prometheus metrics server (MINTRY_OTEL_ENABLED=1)
    _telemetry.start_metrics_server()

    if os.environ.get("MINTRY_JSON_LOGS") != "1":
        print(f"\u2728 Mintry Logic Fabric Active | No-GIL: True")

    _global_engine = engine
    return engine


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
