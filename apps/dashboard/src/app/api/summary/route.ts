import { proxyMintryGet } from "@/lib/mintry-api";
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.MINTRY_CONTROL_PLANE_URL || 'https://wudyreicddrqdysplxai.supabase.co';
const supabaseServiceKey = process.env.MINTRY_SERVICE_ROLE_KEY || process.env.MINTRY_CONTROL_PLANE_KEY || 'dummy_key_to_prevent_crash_on_load';

const supabase = createClient(supabaseUrl, supabaseServiceKey);

export async function GET(): Promise<Response> {
  const response = await proxyMintryGet("/api/summary");
  
  if (!response.ok) {
    return response;
  }
  
  try {
    const data = await response.json();
    
    // Fetch latest policy versions from Supabase
    const { data: policies } = await supabase
      .from('policy_bundles')
      .select('agent_id, version')
      .order('version', { ascending: false });
      
    if (policies && data.mandates) {
      // Map agent_id to highest version
      const versionMap: Record<string, number> = {};
      for (const p of policies) {
        if (!versionMap[p.agent_id]) {
          versionMap[p.agent_id] = p.version;
        }
      }
      
      data.mandates = data.mandates.map((m: any) => ({
        ...m,
        policy_version: versionMap[m.id] || null
      }));
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
