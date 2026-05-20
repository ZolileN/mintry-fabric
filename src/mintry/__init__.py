from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet

def init(api_key: str, db_path: str = "~/.mintry/vouchers.db"):
    """
    Initializes the Mintry Logic Fabric globally.
    """
    if not api_key or not isinstance(api_key, str):
        raise ValueError("MINTRY_API_KEY must be a non-empty string.")

    wallet = MintryWallet(db_path=db_path)
    engine = PolicyEngine(wallet)
    engine.api_key = api_key
    interceptor = GlobalHTTPInterceptor(engine)
    
    # Install the global hooks
    interceptor.install()
    
    print(f"✨ Mintry Logic Fabric Active | No-GIL: True")
    return engine



