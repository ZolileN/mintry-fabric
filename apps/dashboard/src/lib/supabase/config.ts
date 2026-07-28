/**
 * Resolve Supabase URL / anon key for dashboard Auth UI.
 * Prefers NEXT_PUBLIC_* (required for browser clients).
 * Server also falls back to MINTRY_CONTROL_PLANE_* names.
 */

export function getSupabaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    process.env.NEXT_PUBLIC_MINTRY_CONTROL_PLANE_URL ||
    (typeof window === "undefined" ? process.env.MINTRY_CONTROL_PLANE_URL : "") ||
    ""
  ).trim();
}

export function getSupabaseAnonKey(): string {
  return (
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_MINTRY_CONTROL_PLANE_KEY ||
    (typeof window === "undefined" ? process.env.MINTRY_CONTROL_PLANE_KEY : "") ||
    ""
  ).trim();
}

export function supabaseAuthConfigured(): boolean {
  return Boolean(getSupabaseUrl() && getSupabaseAnonKey());
}

/** True when browser-safe public env is present (email/password UI can run). */
export function supabaseBrowserAuthConfigured(): boolean {
  return Boolean(
    (process.env.NEXT_PUBLIC_SUPABASE_URL ||
      process.env.NEXT_PUBLIC_MINTRY_CONTROL_PLANE_URL) &&
      (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
        process.env.NEXT_PUBLIC_MINTRY_CONTROL_PLANE_KEY)
  );
}
