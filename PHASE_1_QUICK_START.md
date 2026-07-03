# Phase 1 Integration - Quick Start (5 minutes)

## 🚀 Quick Setup

### 1. Load Supabase Credentials
```bash
cd /home/zolile/Documents/mintry-fabric
source .env.supabase
echo "✓ Environment variables loaded"
```

### 2. Create Database Tables
Go to: https://app.supabase.com → SQL Editor → New Query

**Copy and paste this:**
```sql
CREATE TABLE IF NOT EXISTS policy_bundles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  version integer NOT NULL,
  policy_json jsonb NOT NULL,
  signature text NOT NULL,
  issued_at timestamptz DEFAULT now(),
  issued_by text,
  created_at timestamptz DEFAULT now(),
  UNIQUE(agent_id, version)
);

CREATE TABLE IF NOT EXISTS telemetry_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  mandate_id text NOT NULL,
  action text NOT NULL,
  amount numeric NOT NULL,
  details jsonb,
  recorded_at timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);
```

Then click **Run** ✅

### 3. Generate Keypair
```bash
python3 << 'EOF'
from mintry.core.crypto import generate_policy_keypair
pub, priv = generate_policy_keypair()
print("PUBLIC_KEY:", pub)
print("\nPRIVATE_KEY:", priv)
EOF
```

**Save the output keys for Phase 2** (optional for Phase 1 demo)

### 4. Run Phase 1 Demo
```bash
python phase1_demo.py
```

**Expected output:**
```
✓ Mintry initialized with control plane integration
✓ Policy bundle created and signed (version 1)
✓ Bundle applied to local cache
✓ Policy history: 1 versions
✓ Control plane health: reachable
...
All Six Architecture Principles validated ✓
```

---

## 📊 Verify Data

After running the demo, check Supabase:

1. **Policy Bundles**: https://app.supabase.com → Table Editor → `policy_bundles`
2. **Telemetry**: https://app.supabase.com → Table Editor → `telemetry_events`

Both tables should have data!

---

## 🎯 What Just Happened

✅ **Principle 1: Initialize once** - Called `mintry.init()` once, infrastructure wired in
✅ **Principle 2: Author centrally as versioned fact** - Policy stored immutably in Supabase
✅ **Principle 3: Enforce locally always** - Decisions made against local cache
✅ **Principle 4: Sync async** - Background worker polls Supabase every 20s
✅ **Principle 5: Fail to last-known-good** - Uses cached policy if Supabase unreachable
✅ **Principle 6: Stay deterministic** - All decisions are deterministic, no ML surprises

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot connect to control plane" | Check internet, verify SUPABASE_URL |
| "Tables don't exist" | Run CREATE TABLE statements in SQL Editor |
| "No module named 'mintry'" | Run: `python -m pip install -e .` |
| Dashboard not accessible | Run: `python -c "from mintry.core.dashboard import start_dashboard; start_dashboard()" &` |

---

## 📝 Next Steps

- ✅ Phase 1 complete: Control plane integration with policy versioning
- 🔜 Phase 2: OPA embedded runtime, UI for rollback, multi-agent support
- 🔜 Phase 3: Vercel signer, continuous policy tuning, analytics

---

## 📂 Files Created

- `.env.supabase` - Credentials for sourcing
- `SUPABASE_SETUP.md` - Detailed setup guide
- `setup-supabase-integration.py` - Automated setup script
- `PHASE_1_QUICK_START.md` - This file

Run `source .env.supabase && python phase1_demo.py` to complete Phase 1! 🎉
