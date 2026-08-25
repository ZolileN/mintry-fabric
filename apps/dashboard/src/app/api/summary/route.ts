import { proxyMintryGet } from "@/lib/mintry-api";
import { createClient } from "@supabase/supabase-js";

interface TelemetryRow {
  agent_id: string;
  mandate_id: string;
  action: string;
  amount: number;
  details: { message?: string } | null;
  timestamp: string;
}

/**
 * Summary merges local ledger data with Supabase policy versions and fleet telemetry.
 */
export async function GET(): Promise<Response> {
  const response = await proxyMintryGet("/api/summary");

  if (!response.ok) {
    return response;
  }

  const supabaseUrl = process.env.MINTRY_CONTROL_PLANE_URL;
  const supabaseServiceKey =
    process.env.MINTRY_SERVICE_ROLE_KEY || process.env.MINTRY_CONTROL_PLANE_KEY;

  if (!supabaseUrl || !supabaseServiceKey) {
    return response;
  }

  try {
    const data = await response.json();
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const { data: policies } = await supabase
      .from("policy_bundles")
      .select("agent_id, version")
      .order("version", { ascending: false })
      .limit(200);

    if (policies && data.mandates) {
      const versionMap: Record<string, number> = {};
      for (const p of policies) {
        if (!versionMap[p.agent_id]) {
          versionMap[p.agent_id] = p.version;
        }
      }

      data.mandates = data.mandates.map(
        (m: { id: string; [key: string]: unknown }) => ({
          ...m,
          agent_id: (m.agent_id as string) || m.id,
          policy_version: versionMap[m.id] || versionMap[(m.agent_id as string) || ""] || null,
        })
      );
    }

    const { data: telemetryRows } = await supabase
      .from("telemetry_events")
      .select("agent_id, mandate_id, action, amount, details, timestamp")
      .order("timestamp", { ascending: false })
      .limit(100);

    if (telemetryRows && telemetryRows.length > 0) {
      const fleetSpent = telemetryRows
        .filter((r: TelemetryRow) => r.action === "spend")
        .reduce((sum: number, r: TelemetryRow) => sum + Number(r.amount || 0), 0);

      data.fleet_telemetry = {
        event_count: telemetryRows.length,
        fleet_spent_usd: round4(fleetSpent),
        source: "supabase",
      };

      const fleetHistory = telemetryRows.map((r: TelemetryRow) => ({
        mandate_id: r.mandate_id,
        action: r.action,
        amount: Number(r.amount || 0),
        timestamp: r.timestamp,
        details: r.details?.message || "",
        agent_id: r.agent_id,
      }));

      if (!data.history?.length || data.history.length < 5) {
        data.history = fleetHistory;
        data.telemetry_merged = true;
      } else {
        data.fleet_history = fleetHistory.slice(0, 20);
        data.telemetry_merged = true;
      }
    }

    return new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (err) {
    console.error("Error parsing summary or fetching from supabase:", err);
    return proxyMintryGet("/api/summary");
  }
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}
