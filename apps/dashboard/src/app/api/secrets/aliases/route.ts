import { NextResponse } from "next/server";
import { requireDashboardAuth } from "@/lib/auth";

const ALIAS_RE = /^[A-Z][A-Z0-9_]{1,127}$/;

/**
 * POST /api/secrets/aliases
 *
 * Validate and echo **alias-only** secret references. Mintry never accepts
 * or stores raw provider API keys — aliases resolve on the customer host
 * from env / Vault agent (see mintry.core.secrets).
 *
 * Body: { aliases: [{ alias, provider?, description? }, ...] }
 */
export async function POST(request: Request) {
  const auth = await requireDashboardAuth(request);
  if (!auth.ok) {
    return auth.response;
  }

  try {
    const body = await request.json();
    const aliases = body.aliases;
    if (!Array.isArray(aliases) || aliases.length === 0) {
      return NextResponse.json(
        { error: "aliases must be a non-empty array" },
        { status: 400 }
      );
    }

    const validated: Array<{
      alias: string;
      provider: string;
      description: string;
    }> = [];

    for (const raw of aliases) {
      const alias = String(raw?.alias || "").trim();
      if (!ALIAS_RE.test(alias)) {
        return NextResponse.json(
          {
            error: `invalid alias '${alias}' — use env-var form (e.g. OPENAI_PROD_KEY)`,
          },
          { status: 400 }
        );
      }
      if (alias.startsWith("sk-") || alias.includes("BEGIN")) {
        return NextResponse.json(
          { error: "raw secrets are rejected; store alias names only" },
          { status: 400 }
        );
      }
      // Reject payloads that try to sneak a value field through.
      if (raw?.value || raw?.secret || raw?.api_key) {
        return NextResponse.json(
          {
            error:
              "secret values are not accepted — Mintry stores alias references only",
          },
          { status: 400 }
        );
      }
      validated.push({
        alias,
        provider: String(raw?.provider || ""),
        description: String(raw?.description || ""),
      });
    }

    return NextResponse.json({
      success: true,
      aliases: validated,
      note: "Aliases validated. Resolve on the agent host via env or customer Vault — never sent to Mintry.",
    });
  } catch (error) {
    console.error("Secrets alias error:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
