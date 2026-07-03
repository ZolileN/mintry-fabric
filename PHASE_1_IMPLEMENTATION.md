# Phase 1 Implementation Guide & Testing

## What Was Implemented

This document describes the complete Phase 1 implementation: policy versioning, ES256 signature verification, Supabase control plane integration, batched telemetry, and OPA bundle scaffolding.

### Core Components

#### 1. **Policy Versioning Schema** (`src/mintry/core/wallet.py`)
- Added `policy_versions` table to persist all policy bundles (append-only)
- Immutable records: version, signature, issued_at, issued_by, received_at, applied, rollback_reason
- Enables rollback semantics without rewriting the spend ledger (Principle 2)

#### 2. **ES256 Signature Verification** (`src/mintry/core/crypto.py`)
- `verify_policy_bundle_signature()`: Validates ECDSA P-256 signatures on policy bundles
- `sign_policy_bundle()`: Signs bundles (for testing/control plane)
- `generate_policy_keypair()`: Generates test keypairs
- Never called from enforcement hot path (async only)

#### 3. **Supabase Control Plane Client** (`src/mintry/core/control_plane.py`)
- `SupabaseControlPlaneClient`: Fetches signed policy bundles via REST API
- `post_telemetry_batch()`: Posts decision events in batches
- `health_check()`: Verifies control plane availability
- Reads `MINTRY_CONTROL_PLANE_URL` and `MINTRY_CONTROL_PLANE_KEY` env vars

#### 4. **Policy Sync Integration** (`src/mintry/core/policy_sync.py`)
- Enhanced `PolicyCache` to:
  - Accept optional `MintryWallet` for persistence
  - `get_policy_history()`: Retrieve versioned policies
  - `rollback_to_version()`: Rollback to previous policy (idempotent)
  - `_persist_to_wallet()`: Append policies to wallet database

#### 5. **Batched Telemetry** (`src/mintry/core/telemetry_batch.py`)
- `TelemetryBatcher`: Collects decision events asynchronously
- `record_decision()`: Queue decision (allow/block/throttle) events
- Uploads batches when size OR time threshold reached
- Failed uploads are requeued locally

#### 6. **OPA Bundle Evaluation** (`src/mintry/core/opa.py`)
- `OPABundleEvaluator`: Loads and evaluates OPA (Rego) policies
- Phase 1: In-process evaluation + CLI fallback
- Phase 2: Embedded OPA runtime (no CLI dependency)
- `load_bundle()`, `validate_bundle()`, `evaluate()`

#### 7. **Dashboard Policy Sync Status** (`src/mintry/core/dashboard.py`)
- Updated `/api/summary` to include `policy_sync` object:
  - `policy_version`: Currently enforced policy version
  - `last_synced_at`: Timestamp of last successful sync (visible staleness)
  - `last_sync_error`: Error message if sync failed
  - `control_plane_healthy`: Health check status (Principle 5)

#### 8. **Wired Into init()** (`src/mintry/__init__.py`)
- `mintry.init()` now accepts:
  - `control_plane_url`: Supabase base URL
  - `control_plane_key`: API key for authentication
  - `control_plane_public_key`: ES256 public key for signature verification
  - `policy_sync_interval`: Polling interval in seconds (default: 20s)
- Creates and starts `PolicySyncWorker` in background
- Attaches policy infrastructure to engine for SDK users

---

## Configuration

### Environment Variables

```bash
# Control plane (optional for Phase 1)
MINTRY_CONTROL_PLANE_URL=https://project.supabase.co
MINTRY_CONTROL_PLANE_KEY=eyJ0eXAiOiJKV1QiLCJhbGc...

# Policy sync interval (seconds, default: 20)
MINTRY_POLICY_SYNC_INTERVAL=20

# OPA bundle path (optional)
MINTRY_OPA_BUNDLE_PATH=~/.mintry/opa_bundle.json

# Telemetry batch settings
MINTRY_TELEMETRY_BATCH_SIZE=100
MINTRY_TELEMETRY_BATCH_INTERVAL=30  # seconds
```

### Programmatic Configuration

```python
import mintry
from mintry.core.crypto import generate_policy_keypair

# Generate keypair for testing
private_pem, public_pem = generate_policy_keypair()

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
    control_plane_url="https://project.supabase.co",
    control_plane_key="your_api_key",
    control_plane_public_key=public_pem,
    policy_sync_interval=20.0,
)

# Access policy infrastructure
print(f"Policy version: {engine.policy_cache.get_sync_status()['policy_version']}")
```

---

## Testing

### Unit Tests

```bash
# All tests
uv run pytest tests/ -v

# Specific modules
uv run pytest tests/test_crypto.py -v
uv run pytest tests/test_control_plane.py -v
uv run pytest tests/test_opa.py -v
uv run pytest tests/test_telemetry_batch.py -v
uv run pytest tests/test_policy_sync.py -v
```

### Integration Test: Full Policy Sync

```python
import mintry
from mintry.core.policy_sync import PolicyBundle
from mintry.core.control_plane import SupabaseControlPlaneClient

# Initialize engine with mocked control plane
engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

# Manually inject a policy (testing before control plane is live)
bundle = PolicyBundle(
    version=1,
    mandates={"agent_1": {"max_usd": 100.0}},
    signature="test_sig",
    issued_at="2026-01-01T00:00:00Z",
)

engine.policy_cache.apply_bundle(bundle)
print(f"Active policy version: {engine.policy_cache.get_active_policy().version}")

# Verify history and rollback
history = engine.policy_cache.get_policy_history()
print(f"Policy history: {history}")
```

### Integration Test: Telemetry Batching

```python
import mintry
from mintry.core.telemetry_batch import TelemetryBatcher

engine = mintry.init(api_key="dev_key", db_path="test_data/local.db")

# Create batcher
batcher = TelemetryBatcher(
    wallet=engine.wallet,
    control_plane_client=engine.control_plane,
    batch_size=10,
    batch_interval_sec=5,
)

batcher.start()

# Record decisions
for i in range(5):
    batcher.record_decision(
        mandate_id="agent_1",
        action="allow",
        amount=0.01,
        details=f"Request {i} approved",
    )

# Wait for batch upload
import time
time.sleep(6)

batcher.stop()
print("Telemetry batch uploaded")
```

### Demo: Full Stack

```bash
# Terminal 1: Start the Gemini mock server (baseline latency)
go run tools/gemini-mock-server/main.go

# Terminal 2: Start dashboard with policy sync enabled
MINTRY_CONTROL_PLANE_URL=https://project.supabase.co \
MINTRY_CONTROL_PLANE_KEY=your_key \
uv run mintry dashboard --db test_data/demo.db

# Terminal 3: Start the Next.js dashboard UI
cd apps/dashboard && npm run dev

# Terminal 4: Run a smoke test
uv run python smoke_test.py
```

---

## Architecture Principles Compliance

| Principle | Status | Verification |
|-----------|--------|--------------|
| 1. Initialize once | ✅ | `mintry.init()` once, no further code changes needed |
| 2. Author centrally, as versioned fact | ✅ | `policy_versions` table (append-only, never mutated) |
| 3. Enforce locally, always | ✅ | `PolicyCache.get_active_policy()` is synchronous, no network on hot path |
| 4. Sync asynchronously, on stated interval | ✅ | `PolicySyncWorker` background thread, visible staleness in dashboard |
| 5. Fail to last-known-good, never open | ✅ | Signature verification + persisted cache; invalid policies rejected |
| 6. Stay deterministic | ✅ | All enforcement decisions are "allow", "block", or configured numbers |

---

## Next Steps: Phase 2

1. **OPA Runtime Integration**: Replace CLI evaluation with embedded OPA engine
2. **Versioned Policy Records**: Expose full history and rollback UI in dashboard
3. **Vercel Control Plane**: Deploy Supabase-backed policy editor + signer
4. **Sidecar Proxy**: Go/Rust proxy for high-throughput environments
5. **Continuous Policy Tuning**: Analytics + automatic policy optimization
6. **Multi-Agent Policies**: Single policy bundle for many agents
7. **Policy Composition**: Mix OPA + budget rules

---

## Known Limitations (Phase 1)

- ❌ OPA evaluation is in-process; requires `opa` CLI for full Rego support
- ❌ Control plane endpoints not yet deployed (Supabase integration pending)
- ❌ Telemetry requires manual Supabase table creation (`telemetry_events`)
- ❌ No UI for policy versioning or rollback yet
- ❌ Policy sync fetches a fixed agent ID (`"default_agent"`)
- ❌ ES256 keypair must be managed externally (no key rotation in Phase 1)

---

## Files Modified/Created

### New Files
- `src/mintry/core/crypto.py` — ES256 signature verification
- `src/mintry/core/control_plane.py` — Supabase control plane client
- `src/mintry/core/telemetry_batch.py` — Async telemetry batching
- `src/mintry/core/opa.py` — OPA bundle evaluation (scaffold)
- `tests/test_crypto.py` — Crypto module tests
- `tests/test_control_plane.py` — Control plane tests
- `tests/test_telemetry_batch.py` — Telemetry batcher tests
- `tests/test_opa.py` — OPA evaluator tests

### Modified Files
- `src/mintry/__init__.py` — Wired PolicySyncWorker into `mintry.init()`
- `src/mintry/core/wallet.py` — Added `policy_versions` table schema
- `src/mintry/core/policy_sync.py` — Added history + rollback + wallet persistence
- `src/mintry/core/dashboard.py` — Exposed policy sync status in `/api/summary`
- `tests/test_policy_sync.py` — Added rollback and history tests
