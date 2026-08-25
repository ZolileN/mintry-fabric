import { proxyMintryPost } from "@/lib/mintry-api";
import { requireDashboardAuth } from "@/lib/auth";

/** Fire a test alert through configured notification channels. */
export async function POST(request: Request): Promise<Response> {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }
  const body = await request.json().catch(() => ({}));
  const payload = JSON.stringify({
    event: "test_alert",
    mandate_id: body.mandate_id || "test_agent",
    threshold_pct: 80,
    budget_usd: 100,
    spent_usd: 85,
    utilization_pct: 85,
    message: "Test notification from Mintry dashboard",
  });
  const upstream = await fetch(
    new URL("/api/alerts/test", process.env.MINTRY_DASHBOARD_API_ORIGIN || "http://127.0.0.1:8000"),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(process.env.MINTRY_DASHBOARD_API_TOKEN
          ? { Authorization: `Bearer ${process.env.MINTRY_DASHBOARD_API_TOKEN}` }
          : {}),
      },
      body: payload,
      cache: "no-store",
    },
  );
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
