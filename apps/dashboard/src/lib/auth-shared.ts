import { NextResponse } from "next/server";
import { supabaseAuthConfigured } from "@/lib/supabase/config";

export const ADMIN_COOKIE = "mintry_dashboard_auth";

export type AuthResult =
  | {
      ok: true;
      subject: string;
      method: "admin_token" | "admin_cookie" | "supabase" | "local_dev";
    }
  | { ok: false; response: NextResponse };

export function timingSafeEqual(a: string, b: string): boolean {
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

export { supabaseAuthConfigured };

export function authRequired(): boolean {
  if (process.env.MINTRY_REQUIRE_AUTH === "1") {
    return true;
  }
  if (
    process.env.NODE_ENV === "production" &&
    (adminTokenConfigured() || supabaseAuthConfigured())
  ) {
    return true;
  }
  return false;
}

/** Optional allowlist: comma-separated emails. Empty = any authenticated user. */
export function allowedEmails(): string[] {
  const raw = process.env.MINTRY_DASHBOARD_ALLOWED_EMAILS || "";
  return raw
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function emailAllowed(email: string | null | undefined): boolean {
  if (!email) return false;
  const list = allowedEmails();
  if (list.length === 0) return true;
  return list.includes(email.trim().toLowerCase());
}
