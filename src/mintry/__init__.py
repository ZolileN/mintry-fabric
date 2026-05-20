import os
from contextlib import contextmanager
from typing import Optional

from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet
from mintry.core.exceptions import MintryMandateExceeded

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
) -> PolicyEngine:
    """
    Initializes the Mintry Logic Fabric globally.

    If ``api_key`` is not provided, falls back to the ``MINTRY_API_KEY``
    environment variable.
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

    # Install the global hooks
    interceptor.install()

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
