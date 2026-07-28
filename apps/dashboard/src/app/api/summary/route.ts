import { proxyMintryGet } from "@/lib/mintry-api";
import { createClient } from "@supabase/supabase-js";

/**
 * Summary is readable without auth in local/dev so the UI can load.
 * Mutating routes require auth when configured.
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
          policy_version: versionMap[m.id] || null,
        })
      );
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
