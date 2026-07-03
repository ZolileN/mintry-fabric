#!/usr/bin/env python3
"""
Supabase Integration Setup for Mintry Fabric Phase 1
Creates required tables and generates ES256 keypair.

SECRETS: All credentials are read from environment variables.
         Never hardcode keys in source files.

Required env vars (set in .env or export before running):
  MINTRY_CONTROL_PLANE_URL   — Supabase project URL
  MINTRY_CONTROL_PLANE_KEY   — Supabase anon key
  MINTRY_SERVICE_ROLE_KEY    — Supabase service role key (for write operations)

Quick start:
  source .env && python setup-supabase-integration.py
"""

import os
import sys


def require_env(name: str) -> str:
    """Read a required env var or exit with a helpful message."""
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"✗ Missing required environment variable: {name}")
        print()
        print("  Set it in your .env file and run:  source .env")
        print("  Or export it directly:              export {name}=<value>")
        sys.exit(1)
    return value


def setup_supabase():
    """Set up Supabase integration and create tables."""
    print("=" * 70)
    print("Mintry Fabric Phase 1 - Supabase Integration Setup")
    print("=" * 70)
    print()

    # Step 1: Read credentials from environment
    print("Step 1: Loading credentials from environment...")
    supabase_url = require_env("MINTRY_CONTROL_PLANE_URL")
    anon_key = require_env("MINTRY_CONTROL_PLANE_KEY")
    # Service role key is optional — used for write operations only
    service_role_key = os.environ.get("MINTRY_SERVICE_ROLE_KEY", anon_key)

    print(f"✓ MINTRY_CONTROL_PLANE_URL={supabase_url}")
    print("✓ MINTRY_CONTROL_PLANE_KEY=<loaded from env>")
    print("✓ MINTRY_SERVICE_ROLE_KEY=<loaded from env>")
    print()

    # Step 2: Test control plane connectivity
    print("Step 2: Testing control plane connectivity...")
    try:
        from mintry.core.control_plane import SupabaseControlPlaneClient

        client = SupabaseControlPlaneClient()
        is_healthy = client.health_check()
        if is_healthy:
            print("✓ Control plane is reachable")
        else:
            print("⚠ Control plane health check inconclusive (may still work)")
    except Exception as e:
        print(f"⚠ Could not import or test control plane: {e}")
    print()

    # Step 3: Generate ES256 keypair
    print("Step 3: Generating ES256 keypair...")
    try:
        from mintry.core.crypto import generate_policy_keypair

        public_key_pem, private_key_pem = generate_policy_keypair()
        print("✓ Keypair generated successfully")
        print()
    except Exception as e:
        print(f"✗ Failed to generate keypair: {e}")
        return False

    # Step 4: Output configuration for .env
    print("=" * 70)
    print("CONFIGURATION COMPLETE — add these to your .env file:")
    print("=" * 70)
    print()
    print(f"MINTRY_CONTROL_PLANE_URL={supabase_url}")
    print("MINTRY_CONTROL_PLANE_KEY=<already in .env>")
    print("MINTRY_SERVICE_ROLE_KEY=<already in .env>")
    print()
    print("# New keys — add these too:")
    print("MINTRY_POLICY_PUBLIC_KEY=<paste-below>")
    print("-" * 70)
    print(public_key_pem)
    print("-" * 70)
    print()
    print("MINTRY_POLICY_PRIVATE_KEY=<paste-below>")
    print("-" * 70)
    print(private_key_pem)
    print("-" * 70)
    print()

    # Step 5: Provide SQL for manual table creation
    print("Step 5: Create tables in Supabase SQL Editor")
    print()
    print("Go to https://app.supabase.com → SQL Editor → New Query")
    print("Copy and paste these SQL statements:")
    print()
    print("-- Policy Bundles Table")
    print("""CREATE TABLE IF NOT EXISTS policy_bundles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  version integer NOT NULL,
  policy_json jsonb NOT NULL,
  signature text NOT NULL,
  issued_at timestamptz DEFAULT now(),
  issued_by text,
  created_at timestamptz DEFAULT now(),
  UNIQUE(agent_id, version)
);""")
    print()
    print("-- Telemetry Events Table")
    print("""CREATE TABLE IF NOT EXISTS telemetry_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id text NOT NULL,
  mandate_id text NOT NULL,
  action text NOT NULL,
  amount numeric NOT NULL,
  details jsonb,
  timestamp timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);""")
    print()
    print("=" * 70)
    print("Next steps:")
    print("  1. Create the tables above in Supabase SQL Editor")
    print("  2. Add the new keys to your .env file")
    print("  3. Run: source .env && python phase1_demo.py")
    print("=" * 70)
    print()

    return True


if __name__ == "__main__":
    success = setup_supabase()
    sys.exit(0 if success else 1)
