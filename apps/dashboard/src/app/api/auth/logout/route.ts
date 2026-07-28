import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { ADMIN_COOKIE } from "@/lib/auth-shared";

/** Sign out Supabase session and clear admin break-glass cookie. */
export async function POST() {
  const supabase = await createClient();
  if (supabase) {
    await supabase.auth.signOut();
  }
  const response = NextResponse.json({ success: true });
  response.cookies.set({
    name: ADMIN_COOKIE,
    value: "",
    httpOnly: true,
    path: "/",
    maxAge: 0,
  });
  return response;
}
