import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";
import {
  ADMIN_COOKIE,
  AuthResult,
  authRequired,
  emailAllowed,
  supabaseAuthConfigured,
  timingSafeEqual,
} from "@/lib/auth-shared";

export {
  ADMIN_COOKIE,
  adminTokenConfigured,
  authRequired,
  emailAllowed,
  supabaseAuthConfigured,
  allowedEmails,
  timingSafeEqual,
} from "@/lib/auth-shared";
export type { AuthResult } from "@/lib/auth-shared";

/**
 * Require dashboard auth for mutating / privileged API routes.
 *
 * Accepted credentials (first match wins):
 * 1. Authorization: Bearer <MINTRY_DASHBOARD_ADMIN_TOKEN>
 * 2. httpOnly admin cookie from POST /api/login
 * 3. Supabase Auth session (cookie) — subject = user email
 * 4. When auth is not required (local/dev), allow with local_dev subject
 */
export async function requireDashboardAuth(request: Request): Promise<AuthResult> {
  const adminToken = process.env.MINTRY_DASHBOARD_ADMIN_TOKEN;
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.toLowerCase().startsWith("bearer ")
    ? authHeader.slice(7).trim()
    : "";

  if (adminToken && bearer && timingSafeEqual(bearer, adminToken)) {
    return { ok: true, subject: "admin_token", method: "admin_token" };
  }

  if (adminToken) {
    try {
      const jar = await cookies();
      const cookieVal = jar.get(ADMIN_COOKIE)?.value || "";
      if (cookieVal && timingSafeEqual(cookieVal, adminToken)) {
        return { ok: true, subject: "admin_cookie", method: "admin_cookie" };
      }
    } catch {
      // cookies() unavailable in some test contexts
    }
  }

  if (supabaseAuthConfigured()) {
    try {
      const supabase = await createSupabaseServerClient();
      if (supabase) {
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user?.email) {
          if (!emailAllowed(user.email)) {
            return {
              ok: false,
              response: NextResponse.json(
                {
                  error:
                    "Forbidden — email is not on MINTRY_DASHBOARD_ALLOWED_EMAILS",
                },
                { status: 403 }
              ),
            };
          }
          return {
            ok: true,
            subject: user.email,
            method: "supabase",
          };
        }
      }
    } catch {
      // fall through
    }
  }

  if (authRequired()) {
    return {
      ok: false,
      response: NextResponse.json(
        {
          error:
            "Unauthorized — sign in at /login (Supabase Auth), or use admin token via POST /api/login / Authorization: Bearer …",
        },
        { status: 401 }
      ),
    };
  }

  return { ok: true, subject: "local_dev_unauthenticated", method: "local_dev" };
}
