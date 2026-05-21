import { proxyMintryGet } from "@/lib/mintry-api";

export async function GET(): Promise<Response> {
  return proxyMintryGet("/api/summary");
}
