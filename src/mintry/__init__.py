from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet

from typing import Optional

def init(api_key: str, db_path: str = "~/.mintry/vouchers.db", webhook_url: Optional[str] = None):
    """
    Initializes the Mintry Logic Fabric globally.
    """
    if not api_key or not isinstance(api_key, str):
        raise ValueError("MINTRY_API_KEY must be a non-empty string.")

    wallet = MintryWallet(db_path=db_path)
    engine = PolicyEngine(wallet, webhook_url=webhook_url)
    engine.api_key = api_key
    interceptor = GlobalHTTPInterceptor(engine)
    
    # Install the global hooks
    interceptor.install()
    
    import os
    if os.environ.get("MINTRY_JSON_LOGS") != "1":
        print(f"✨ Mintry Logic Fabric Active | No-GIL: True")
    return engine



