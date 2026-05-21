import { proxyMintryPost } from "@/lib/mintry-api";

export async function POST(request: Request): Promise<Response> {
  return proxyMintryPost("/api/mandates/upsert", request);
}
