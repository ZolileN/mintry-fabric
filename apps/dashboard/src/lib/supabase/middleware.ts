import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseAnonKey, getSupabaseUrl } from "./config";

/**
 * Refresh Supabase Auth cookies on the request/response pair.
 * Returns the (possibly mutated) response and the current user email if any.
 */
export async function updateSession(request: NextRequest): Promise<{
  response: NextResponse;
  userEmail: string | null;
  userId: string | null;
}> {
  let response = NextResponse.next({
    request: { headers: request.headers },
  });

  const url = getSupabaseUrl();
  const key = getSupabaseAnonKey();
  if (!url || !key) {
    return { response, userEmail: null, userId: null };
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value)
        );
        response = NextResponse.next({
          request: { headers: request.headers },
        });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options)
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return {
    response,
    userEmail: user?.email ?? null,
    userId: user?.id ?? null,
  };
}
