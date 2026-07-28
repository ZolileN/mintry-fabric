import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  ADMIN_COOKIE,
  adminTokenConfigured,
  authRequired,
  supabaseAuthConfigured,
} from "@/lib/auth-shared";
import { cookies } from "next/headers";

/** Current dashboard session (Supabase user and/or admin cookie). */
export async function GET() {
  let email: string | null = null;
  let userId: string | null = null;
  let method: "supabase" | "admin_cookie" | "none" = "none";

  if (supabaseAuthConfigured()) {
    const supabase = await createClient();
    if (supabase) {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (user) {
        email = user.email ?? null;
        userId = user.id;
        method = "supabase";
      }
    }
  }

  if (method === "none" && adminTokenConfigured()) {
    try {
      const jar = await cookies();
      const val = jar.get(ADMIN_COOKIE)?.value || "";
      if (val && val === process.env.MINTRY_DASHBOARD_ADMIN_TOKEN) {
        method = "admin_cookie";
        email = "admin";
      }
    } catch {
      /* ignore */
    }
  }

  return NextResponse.json({
    authenticated: method !== "none",
    method,
    email,
    user_id: userId,
    auth_required: authRequired(),
    supabase_configured: supabaseAuthConfigured(),
    admin_token_configured: adminTokenConfigured(),
  });
}
