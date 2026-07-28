import { NextResponse } from "next/server";
import { requireDashboardAuth } from "@/lib/auth";

/**
 * POST /api/orgs/compile
 *
 * Compile Company → department → project → agent hierarchy into flat
 * agent caps (and optional fleet partition plan). Inheritance resolves
 * here — never on the authorize hot path.
 *
 * Body: { org: OrgNode, fleet_id?: string, push?: boolean }
 * When push=true and fleet_id set, forwards to /api/fleets/partition.
 */
export async function POST(request: Request) {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }

  try {
    const body = await request.json();
    const org = body.org;
    const fleetId = typeof body.fleet_id === "string" ? body.fleet_id : "";
    const push = Boolean(body.push);

    if (!org || typeof org !== "object") {
      return NextResponse.json({ error: "org tree is required" }, { status: 400 });
    }

    // Compile via Python-compatible rules inlined (keep dashboard self-contained).
    const compiled = compileOrg(org);
    if (!compiled.ok) {
      return NextResponse.json({ error: compiled.error }, { status: 400 });
    }

    const result: Record<string, unknown> = {
      success: true,
      agent_caps: compiled.caps,
      total_usd: compiled.total,
      allocated_usd: compiled.allocated,
    };

    if (push) {
      if (!fleetId) {
        return NextResponse.json(
          { error: "fleet_id is required when push=true" },
          { status: 400 }
        );
      }
      const origin = new URL(request.url).origin;
      const partitionRes = await fetch(`${origin}/api/fleets/partition`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: request.headers.get("cookie") || "",
          authorization: request.headers.get("authorization") || "",
        },
        body: JSON.stringify({
          fleet_id: fleetId,
          total_usd: compiled.total,
          partitions: compiled.caps,
        }),
      });
      const partitionJson = await partitionRes.json();
      if (!partitionRes.ok) {
        return NextResponse.json(
          { error: partitionJson.error || "fleet partition push failed", compiled: result },
          { status: partitionRes.status }
        );
      }
      result.fleet = partitionJson;
    }

    return NextResponse.json(result);
  } catch (error) {
    console.error("Org compile error:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

type OrgNode = {
  id?: string;
  kind?: string;
  budget_usd?: number | null;
  children?: OrgNode[];
};

function compileOrg(
  root: OrgNode
):
  | { ok: true; caps: Record<string, number>; total: number; allocated: number }
  | { ok: false; error: string } {
  if (root.kind !== "company") {
    return { ok: false, error: "org root must be kind='company'" };
  }
  if (typeof root.budget_usd !== "number" || !Number.isFinite(root.budget_usd)) {
    return { ok: false, error: "company root must declare budget_usd" };
  }
  const caps: Record<string, number> = {};
  const err = collect(root, root.budget_usd, caps);
  if (err) return { ok: false, error: err };
  if (Object.keys(caps).length === 0) {
    return { ok: false, error: "org tree produced no agent caps" };
  }
  const allocated = Object.values(caps).reduce((a, b) => a + b, 0);
  return { ok: true, caps, total: root.budget_usd, allocated };
}

function collect(
  node: OrgNode,
  parentBudget: number,
  out: Record<string, number>
): string | null {
  const id = String(node.id || "").trim();
  if (!id) return "org node missing id";
  if (!["company", "department", "project", "agent"].includes(String(node.kind))) {
    return `org node '${id}' has invalid kind`;
  }
  const own =
    typeof node.budget_usd === "number" && Number.isFinite(node.budget_usd)
      ? node.budget_usd
      : parentBudget;
  if (typeof node.budget_usd === "number" && node.budget_usd > parentBudget + 1e-9) {
    return `node '${id}' budget exceeds parent budget`;
  }
  if (node.kind === "agent") {
    if (id in out) return `duplicate agent id: '${id}'`;
    out[id] = Math.round(own * 1e6) / 1e6;
    return null;
  }
  const children = node.children || [];
  if (children.length === 0) return `non-agent node '${id}' has no children`;
  const explicit = children.filter((c) => typeof c.budget_usd === "number");
  const implicit = children.filter((c) => typeof c.budget_usd !== "number");
  const explicitSum = explicit.reduce((a, c) => a + Number(c.budget_usd), 0);
  if (explicitSum > own + 1e-9) {
    return `children of '${id}' explicit budgets exceed node budget`;
  }
  const remainder = own - explicitSum;
  const perImplicit = implicit.length ? remainder / implicit.length : 0;
  for (const child of children) {
    const childParent =
      typeof child.budget_usd === "number" ? Number(child.budget_usd) : perImplicit;
    const err = collect(child, childParent, out);
    if (err) return err;
  }
  return null;
}
