import { NextResponse, type NextRequest } from "next/server";
import {
  ADMIN_COOKIE,
  authRequired,
  adminTokenConfigured,
  timingSafeEqual,
} from "@/lib/auth-shared";
import { supabaseAuthConfigured } from "@/lib/supabase/config";
import { updateSession } from "@/lib/supabase/middleware";

const PUBLIC_PATHS = ["/login", "/auth/callback"];

function isPublic(pathname: string): boolean {
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return true;
  }
  if (pathname.startsWith("/api/login") || pathname.startsWith("/api/auth/")) {
    return true;
  }
  if (
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico" ||
    pathname === "/icon.svg"
  ) {
    return true;
  }
  return false;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const { response, userEmail } = await updateSession(request);

  if (pathname.startsWith("/api/")) {
    return response;
  }

  const gateUi =
    authRequired() ||
    (process.env.NODE_ENV === "production" && supabaseAuthConfigured());

  if (!gateUi || isPublic(pathname)) {
    if (pathname === "/login" && userEmail) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return response;
  }

  const adminToken = process.env.MINTRY_DASHBOARD_ADMIN_TOKEN || "";
  const adminCookie = request.cookies.get(ADMIN_COOKIE)?.value || "";
  const hasAdminCookie =
    adminTokenConfigured() &&
    Boolean(adminCookie) &&
    timingSafeEqual(adminCookie, adminToken);

  if (userEmail || hasAdminCookie) {
    if (pathname === "/login") {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return response;
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
