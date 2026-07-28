import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import {
  allowMockSignatures,
  requirePolicySignatures,
  resolvePolicyPrivateKey,
  signPolicyBundleCanonical,
} from "@/lib/policy-crypto";
import { requireDashboardAuth } from "@/lib/auth";
import { mandateRuleForShare, validatePartitions } from "@/lib/fleet";

const supabaseUrl = process.env.MINTRY_CONTROL_PLANE_URL || "";
const supabaseServiceKey =
  process.env.MINTRY_SERVICE_ROLE_KEY || process.env.MINTRY_CONTROL_PLANE_KEY || "";

/**
 * POST /api/fleets/partition
 *
 * Fleet Option A: validate static partitions, then sign & push one policy
 * bundle per agent (immutable versions). Agents enforce only their local
 * max_usd — no shared counter on the hot path.
 *
 * Body: { fleet_id, total_usd, partitions: { [agent_id]: share_usd } }
 */
export async function POST(request: Request) {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }

  try {
    if (!supabaseUrl || !supabaseServiceKey) {
      return NextResponse.json(
        { error: "Control plane is not configured" },
        { status: 503 }
      );
    }

    const body = await request.json();
    const fleetId = typeof body.fleet_id === "string" ? body.fleet_id : "";
    const totalUsd = body.total_usd;
    const partitions = body.partitions;

    const plan = validatePartitions(totalUsd, partitions || {}, { fleetId });
    if (!plan.ok) {
      return NextResponse.json({ error: plan.error }, { status: 400 });
    }
    if (!plan.fleet_id) {
      return NextResponse.json({ error: "fleet_id is required" }, { status: 400 });
    }

    const supabase = createClient(supabaseUrl, supabaseServiceKey);
    const privateKey = resolvePolicyPrivateKey();
    const issuedAt = new Date().toISOString();
    const issuedBy = auth.subject || "vercel_dashboard_fleet_signer";

    const results: Array<{
      agent_id: string;
      version: number;
      share_usd: number;
    }> = [];

    for (const [agentId, shareUsd] of Object.entries(plan.partitions)) {
      const { data: latestPolicy, error: fetchError } = await supabase
        .from("policy_bundles")
        .select("version")
        .eq("agent_id", agentId)
        .order("version", { ascending: false })
        .limit(1)
        .single();

      let newVersion = 1;
      if (latestPolicy) {
        newVersion = latestPolicy.version + 1;
      } else if (fetchError && fetchError.code !== "PGRST116") {
        console.error("Error fetching latest policy:", fetchError);
        return NextResponse.json(
          {
            error: `Failed to fetch latest policy for agent ${agentId}`,
            pushed: results,
          },
          { status: 500 }
        );
      }

      const mandates = {
        [agentId]: mandateRuleForShare(shareUsd, {
          fleetId: plan.fleet_id,
          fleetTotalUsd: plan.total_usd,
        }),
      };

      const signingPayload = {
        version: newVersion,
        mandates,
        issued_at: issuedAt,
        issued_by: issuedBy,
      };

      let signature: string;
      if (privateKey) {
        signature = signPolicyBundleCanonical(signingPayload, privateKey);
      } else if (allowMockSignatures() && !requirePolicySignatures()) {
        console.warn(
          "[mintry] Fleet partition signing with mock signature (MINTRY_ALLOW_MOCK_SIGNATURES=1)"
        );
        signature = "mock_signature_for_fleet_partition";
      } else {
        return NextResponse.json(
          {
            error:
              "MINTRY_POLICY_PRIVATE_KEY is required to sign fleet partitions. " +
              "For local spike-only use set MINTRY_ALLOW_MOCK_SIGNATURES=1.",
            pushed: results,
          },
          { status: 500 }
        );
      }

      const { error: insertError } = await supabase.from("policy_bundles").insert([
        {
          agent_id: agentId,
          version: newVersion,
          policy_json: mandates,
          signature,
          issued_at: issuedAt,
          issued_by: issuedBy,
        },
      ]);

      if (insertError) {
        console.error("Error inserting fleet policy:", insertError);
        return NextResponse.json(
          {
            error: `Failed to save policy for agent ${agentId}`,
            detail: insertError.message,
            pushed: results,
          },
          { status: 500 }
        );
      }

      results.push({ agent_id: agentId, version: newVersion, share_usd: shareUsd });
    }

    return NextResponse.json({
      success: true,
      fleet_id: plan.fleet_id,
      total_usd: plan.total_usd,
      allocated_usd: plan.allocated_usd,
      unallocated_usd: plan.unallocated_usd,
      agents: results,
    });
  } catch (error) {
    console.error("Fleet partition error:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
