import pytest
import os
import mintry
from mintry.core.exceptions import MintryMandateExceeded
from mintry.interceptors.global_http import GlobalHTTPInterceptor

@pytest.fixture(autouse=True)
def isolate_fabric(tmp_path):
    """Reset the interceptor and clear env vars for every test."""
    GlobalHTTPInterceptor._reset()
    mintry._global_engine = None
    if "MINTRY_API_KEY" in os.environ:
        del os.environ["MINTRY_API_KEY"]
    yield
    GlobalHTTPInterceptor._reset()
    mintry._global_engine = None
    if "MINTRY_API_KEY" in os.environ:
        del os.environ["MINTRY_API_KEY"]


def test_mintry_mandate_exceeded_attributes():
    """Verify MintryMandateExceeded has the expected attributes."""
    try:
        raise MintryMandateExceeded(task="test_task", cap=50.0, spent=10.0)
    except MintryMandateExceeded as e:
        assert e.task == "test_task"
        assert e.cap == 50.0
        assert e.spent == 10.0
        
        # Verify it can be caught as PermissionError
        assert isinstance(e, PermissionError)


def test_init_with_env_var(tmp_path, monkeypatch):
    """Verify mintry.init() auto-loads MINTRY_API_KEY from environment."""
    monkeypatch.setenv("MINTRY_API_KEY", "env_test_key")
    db = str(tmp_path / "vouchers.db")
    
    engine = mintry.init(db_path=db)
    assert engine.api_key == "env_test_key"
    assert mintry._global_engine is engine


def test_three_line_syntax(tmp_path, monkeypatch):
    """Verify the marketing site's 3-line syntax works."""
    monkeypatch.setenv("MINTRY_API_KEY", "marketing_test_key")
    db = str(tmp_path / "vouchers.db")
    
    # Line 1: import mintry (already done)
    # Line 2: mintry.init()
    mintry.init(db_path=db)
    
    # Line 3: with mintry.mandate(...)
    with mintry.mandate("task:nightly_summarizer", cap=50.00) as m:
        assert m.task == "task:nightly_summarizer"
        assert m.max_usd == 50.00
        assert m.id.startswith("mt_")
        
        # Verify it was added to the DB
        data = mintry._global_engine.wallet.get_mandate(m.id)
        assert data["budget_usd"] == 50.00


def test_auto_init_on_mandate(tmp_path, monkeypatch):
    """Verify mintry.mandate() auto-initializes if the env var is present."""
    monkeypatch.setenv("MINTRY_API_KEY", "auto_init_key")
    # Note: we don't pass db_path, so it uses the default ~/.mintry/vouchers.db
    # We shouldn't actually run this and mess up the user's home dir if we can avoid it.
    # Actually, we can monkeypatch os.path.expanduser or something, but let's just 
    # ensure it doesn't fail due to key errors.
    
    # We will mock MintryWallet to avoid DB creation in ~
    class MockWallet:
        def __init__(self, db_path):
            self.db_path = db_path
    
    class MockEngine:
        def __init__(self, wallet, webhook_url=None):
            self.api_key = None
            self.wallet = wallet
        def shield(self, task, max_usd):
            return (task, max_usd)
            
    class MockInterceptor:
        def __init__(self, engine):
            pass
        def install(self):
            pass

    monkeypatch.setattr(mintry, "MintryWallet", MockWallet)
    monkeypatch.setattr(mintry, "PolicyEngine", MockEngine)
    monkeypatch.setattr(mintry, "GlobalHTTPInterceptor", MockInterceptor)
    
    # The actual test
    assert mintry._global_engine is None
    
    res = mintry.mandate("auto_task", cap=10.0)
    
    assert res == ("auto_task", 10.0)
    assert mintry._global_engine is not None
    assert mintry._global_engine.api_key == "auto_init_key"
