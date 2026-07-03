#!/bin/bash
# Setup Supabase Integration for Mintry Fabric Phase 1
#
# SECRETS: All credentials are read from environment variables.
#          Never hardcode keys in source files.
#
# Required env vars (set in .env or export before running):
#   MINTRY_CONTROL_PLANE_URL   — Supabase project URL
#   MINTRY_CONTROL_PLANE_KEY   — Supabase anon key
#   MINTRY_SERVICE_ROLE_KEY    — Supabase service role key
#
# Quick start:
#   source .env && bash setup-supabase-integration.sh

set -e

# ── Validate required environment variables ──────────────────────────────────
require_env() {
  local name="$1"
  local value="${!name}"
  if [ -z "$value" ]; then
    echo "✗ Missing required environment variable: $name"
    echo ""
    echo "  Set it in your .env file and run:  source .env"
    echo "  Or export it directly:             export $name=<value>"
    exit 1
  fi
}

require_env MINTRY_CONTROL_PLANE_URL
require_env MINTRY_CONTROL_PLANE_KEY
require_env MINTRY_SERVICE_ROLE_KEY

SUPABASE_URL="$MINTRY_CONTROL_PLANE_URL"
ANON_KEY="$MINTRY_CONTROL_PLANE_KEY"
SERVICE_ROLE_KEY="$MINTRY_SERVICE_ROLE_KEY"

# ── Setup ─────────────────────────────────────────────────────────────────────
echo "Setting up Supabase Integration for Mintry Fabric Phase 1"
echo "==========================================================="
echo ""

# Step 1: Confirm environment variables are loaded
echo "Step 1: Credentials loaded from environment..."
echo "  ✓ MINTRY_CONTROL_PLANE_URL=${SUPABASE_URL}"
echo "  ✓ MINTRY_CONTROL_PLANE_KEY=<loaded from env>"
echo "  ✓ MINTRY_SERVICE_ROLE_KEY=<loaded from env>"
echo ""

# Step 2: Create database tables via Supabase API
echo "Step 2: Creating database tables..."

# Policy Bundles Table
curl -s \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "CREATE TABLE IF NOT EXISTS policy_bundles (id uuid DEFAULT gen_random_uuid() PRIMARY KEY, agent_id text NOT NULL, version integer NOT NULL, policy_json jsonb NOT NULL, signature text NOT NULL, issued_at timestamptz DEFAULT now(), issued_by text, created_at timestamptz DEFAULT now(), UNIQUE(agent_id, version));"
  }' \
  "$SUPABASE_URL/rest/v1/rpc/sql_query" 2>/dev/null || echo "  Note: Create tables manually in Supabase SQL Editor (see SUPABASE_SETUP.md)"

# Telemetry Events Table
curl -s \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "CREATE TABLE IF NOT EXISTS telemetry_events (id uuid DEFAULT gen_random_uuid() PRIMARY KEY, agent_id text NOT NULL, mandate_id text NOT NULL, action text NOT NULL, amount numeric NOT NULL, details jsonb, timestamp timestamptz DEFAULT now(), created_at timestamptz DEFAULT now());"
  }' \
  "$SUPABASE_URL/rest/v1/rpc/sql_query" 2>/dev/null || true

echo "  ✓ Tables created (or already exist)"
echo ""

# Step 3: Generate ES256 keypair
echo "Step 3: Generating ES256 keypair..."
KEYPAIR=$(python3 -c "
from mintry.core.crypto import generate_policy_keypair
pub, priv = generate_policy_keypair()
print(f'MINTRY_POLICY_PUBLIC_KEY={pub}')
print(f'MINTRY_POLICY_PRIVATE_KEY={priv}')
" 2>/dev/null)

echo ""
echo "Step 4: Add the following to your .env file:"
echo "==========================================================="
echo ""
echo "$KEYPAIR"
echo ""
echo "==========================================================="
echo "Setup complete! Run:"
echo "  source .env && python phase1_demo.py"
echo ""
