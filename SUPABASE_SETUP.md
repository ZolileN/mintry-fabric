# Supabase Integration Setup Guide - Phase 1

## Your Supabase Details
- **Project URL**: `<YOUR_SUPABASE_URL>`
- **Anon Key**: `<YOUR_ANON_KEY>`
- **Service Role Key**: `<YOUR_SERVICE_ROLE_KEY>`

## Setup Steps

### Step 1: Export Environment Variables

Run in your terminal:
```bash
export MINTRY_CONTROL_PLANE_URL=<YOUR_SUPABASE_URL>
export MINTRY_CONTROL_PLANE_KEY=<YOUR_ANON_KEY>
```

Or add to your `.env` file:
```
MINTRY_CONTROL_PLANE_URL=<YOUR_SUPABASE_URL>
MINTRY_CONTROL_PLANE_KEY=<YOUR_ANON_KEY>
```

### Step 2: Create Database Tables

1. Go to: https://app.supabase.com
2. Select your project: `wudyreicddrqdysplxai`
3. Click **SQL Editor** → **New Query**
4. Paste this SQL and run it:

```sql
-- Policy Bundles Table
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

-- Telemetry Events Table
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

### Step 3: Generate ES256 Keypair

Run this in your terminal:
```bash
cd /home/zolile/Documents/mintry-fabric
python3 << 'EOF'
from mintry.core.crypto import generate_policy_keypair
pub, priv = generate_policy_keypair()
print("=== PUBLIC KEY ===")
print(pub)
print("\n=== PRIVATE KEY ===")
print(priv)
EOF
```

Save the output securely! You'll see output like:
```
=== PUBLIC KEY ===
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
-----END PUBLIC KEY-----

=== PRIVATE KEY ===
-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIIGlq...
-----END EC PRIVATE KEY-----
```

### Step 4: Export Keypair (Optional but Recommended)

Add to your environment:
```bash
export MINTRY_POLICY_PUBLIC_KEY="BEGIN PUBLIC KEY"
export MINTRY_POLICY_PRIVATE_KEY="BEGIN EC PRIVATE KEY-"
```

Or add to `.env`:
```
MINTRY_POLICY_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...
MINTRY_POLICY_PRIVATE_KEY=-----BEGIN EC PRIVATE KEY-----\n...
```

### Step 5: Run Phase 1 Demo

```bash
cd /home/zolile/Documents/mintry-fabric
python phase1_demo.py
```

You should see:
- ✓ Policy cache initialized
- ✓ Control plane client initialized
- ✓ Policy bundle created and signed
- ✓ Bundle applied to cache
- ✓ Policy history retrieved
- ✓ All Six Architecture Principles validated

## Verification

### Check Supabase Tables

After running the demo, verify data was written:

1. **Policy Bundles**: https://app.supabase.com → Table Editor → `policy_bundles`
   - Should see: agent_id, version, policy_json, signature

2. **Telemetry Events**: https://app.supabase.com → Table Editor → `telemetry_events`
   - Should see: agent_id, mandate_id, action, amount

### Check Dashboard

Once running, visit: http://localhost:8000

Look for policy sync status showing:
- `policy_version`: current version
- `last_synced_at`: timestamp of last sync
- `control_plane_healthy`: true/false

## Troubleshooting

### "Cannot connect to control plane"
- Verify `MINTRY_CONTROL_PLANE_URL` is set correctly
- Check internet connectivity
- Verify Supabase project is active: https://app.supabase.com

### "Signature verification failed"
- Only occurs if `MINTRY_POLICY_PUBLIC_KEY` is set
- Either remove it (for Phase 1) or ensure keypair matches
- Public key must correspond to private key used for signing

### "Tables don't exist"
- Go to Supabase SQL Editor and run the CREATE TABLE statements manually
- Check that no error messages appear

### "No modules found"
- Ensure you're in `/home/zolile/Documents/mintry-fabric` directory
- Run `python -m pip install -e .` to install in development mode

## Next Steps

1. ✅ Tables created
2. ✅ Keypair generated
3. ✅ Environment variables set
4. Run Phase 1 demo to validate end-to-end integration
5. Check dashboard for policy sync status
6. Review telemetry data in Supabase

Once Phase 1 is validated, Phase 2 will add:
- OPA embedded runtime
- Policy versioning UI
- Vercel policy signer
- Multi-agent support
- Continuous policy tuning
