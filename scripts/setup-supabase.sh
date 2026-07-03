#!/bin/bash
# Supabase Setup Script for Mintry Control Plane
# Run this after you have a Supabase project created

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Mintry Control Plane: Supabase Setup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Generate keypair
echo -e "${YELLOW}Step 1: Generate ES256 Keypair${NC}"
echo "Creating a new keypair for policy signing..."

KEYPAIR_OUTPUT=$(python3 << 'EOF'
from mintry.core.crypto import generate_policy_keypair

private_pem, public_pem = generate_policy_keypair()

print("=== PRIVATE KEY (keep secret, store in env var) ===")
print(private_pem)
print()
print("=== PUBLIC KEY (share with dashboard/vercel) ===")
print(public_pem)
EOF
)

echo "$KEYPAIR_OUTPUT"
echo ""
echo -e "${YELLOW}⚠️  Save these keys securely!${NC}"
echo ""

# Step 2: Create Supabase tables
echo -e "${YELLOW}Step 2: Create Supabase Tables${NC}"
echo "Create these tables in your Supabase dashboard (SQL Editor):"
echo ""

cat << 'EOF'
-- Policy bundles table (control plane stores policies here)
CREATE TABLE policy_bundles (
  id BIGSERIAL PRIMARY KEY,
  agent_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  policy_json JSONB NOT NULL,
  signature TEXT NOT NULL,
  issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
  issued_by TEXT DEFAULT 'control-plane',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  UNIQUE(agent_id, version)
);

CREATE INDEX idx_policy_bundles_agent_version ON policy_bundles(agent_id, version DESC);

-- Telemetry events table (SDK sends telemetry here)
CREATE TABLE telemetry_events (
  id BIGSERIAL PRIMARY KEY,
  timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
  mandate_id TEXT NOT NULL,
  action TEXT NOT NULL,
  amount REAL DEFAULT 0.0,
  details TEXT,
  agent_id TEXT DEFAULT 'unknown',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX idx_telemetry_agent ON telemetry_events(agent_id, created_at DESC);
CREATE INDEX idx_telemetry_mandate ON telemetry_events(mandate_id, created_at DESC);

-- Give RLS policy if using authentication
ALTER TABLE policy_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_events ENABLE ROW LEVEL SECURITY;

-- For now, allow all (disable RLS for development)
-- In production, use service role key + RLS policies
EOF

echo ""
echo -e "${YELLOW}Step 3: Create API Routes${NC}"
echo "Create these Vercel routes:"
echo ""

cat << 'EOF'
# GET /api/policy/bundles
- Query: SELECT * FROM policy_bundles WHERE agent_id = ?agent_id AND version > ?current_version
- Returns: Latest policy bundle

# POST /api/telemetry/batch
- Body: Array of telemetry event records
- Inserts into telemetry_events table

# GET /health
- Returns: { "status": "ok" }
EOF

echo ""
echo -e "${YELLOW}Step 4: Set Environment Variables${NC}"
echo "Add these to your local .env:"
echo ""

cat << 'EOF'
MINTRY_CONTROL_PLANE_URL=https://project-ref.supabase.co
MINTRY_CONTROL_PLANE_KEY=your_anon_key_here

# Optional: Public key for signature verification
MINTRY_CONTROL_PLANE_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
EOF

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Create the tables above in Supabase (SQL Editor tab)"
echo "2. Get your project URL and anon key (Settings → API tab)"
echo "3. Set the env vars above"
echo "4. Deploy control plane routes to Vercel (optional)"
echo "5. Test with: uv run mintry dashboard --db test_data/demo.db"
echo ""
echo "To test policy sync without Supabase:"
echo "  - Init without control_plane_url/key"
echo "  - Manually apply bundles via API:"
echo ""
echo "    engine.policy_cache.apply_bundle(bundle)"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
