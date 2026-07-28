import { NextResponse } from "next/server";
import { cookies } from "next/headers";

export const ADMIN_COOKIE = "mintry_dashboard_auth";

export type AuthResult =
  | { ok: true; subject: string }
  | { ok: false; response: NextResponse };

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let out = 0;
  for (let i = 0; i < a.length; i++) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

export function adminTokenConfigured(): boolean {
  return Boolean(process.env.MINTRY_DASHBOARD_ADMIN_TOKEN);
}

export function authRequired(): boolean {
  if (process.env.MINTRY_REQUIRE_AUTH === "1") {
    return true;
  }
  if (process.env.NODE_ENV === "production" && adminTokenConfigured()) {
    return true;
  }
  return false;
}

/**
 * Require dashboard admin auth for mutating / privileged API routes.
 *
 * Accepted credentials (first match wins):
 * 1. Authorization: Bearer <MINTRY_DASHBOARD_ADMIN_TOKEN>
 * 2. httpOnly cookie set by POST /api/login
 * 3. When auth is not required (local/dev without token), allow with warning subject
 */
export async function requireDashboardAuth(request: Request): Promise<AuthResult> {
  const adminToken = process.env.MINTRY_DASHBOARD_ADMIN_TOKEN;
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.toLowerCase().startsWith("bearer ")
    ? authHeader.slice(7).trim()
    : "";

  if (adminToken && bearer && timingSafeEqual(bearer, adminToken)) {
    return { ok: true, subject: "admin_token" };
  }

  if (adminToken) {
    try {
      const jar = await cookies();
      const cookieVal = jar.get(ADMIN_COOKIE)?.value || "";
      if (cookieVal && timingSafeEqual(cookieVal, adminToken)) {
        return { ok: true, subject: "admin_cookie" };
      }
    } catch {
      // cookies() unavailable in some test contexts
    }
  }

  if (authRequired()) {
    return {
      ok: false,
      response: NextResponse.json(
        {
          error:
            "Unauthorized — POST /api/login with the admin token, or send Authorization: Bearer …",
        },
        { status: 401 }
      ),
    };
  }

  return { ok: true, subject: "local_dev_unauthenticated" };
}
