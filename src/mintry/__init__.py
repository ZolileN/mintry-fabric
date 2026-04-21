from mintry.interceptors.global_http import GlobalHTTPInterceptor
from mintry.core.engine import PolicyEngine
from mintry.core.wallet import MintryWallet

def init(api_key: str):
    """
    Initializes the Mintry Logic Fabric globally.
    """
    wallet = MintryWallet()
    engine = PolicyEngine(wallet)
    interceptor = GlobalHTTPInterceptor(engine)
    
    # Install the global hooks
    interceptor.install()
    
    print(f"✨ Mintry Logic Fabric Active | No-GIL: True")
    return engine



