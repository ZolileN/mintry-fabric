import { proxyMintryPost } from "@/lib/mintry-api";
import { requireDashboardAuth } from "@/lib/auth";

export async function POST(request: Request): Promise<Response> {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }
  return proxyMintryPost("/api/mandates/revoke", request);
}
