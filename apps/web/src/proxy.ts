import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/cookies";

function withContentSecurityPolicy(response: NextResponse, policy: string) {
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDevelopment = process.env.NODE_ENV === "development";
  const isLocal = process.env.APP_ENV === "local";
  const developmentEval = isDevelopment ? " 'unsafe-eval'" : "";
  const stylePolicy = isLocal ? "style-src 'self'" : `style-src 'self' 'nonce-${nonce}'`;
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${developmentEval}`,
    stylePolicy,
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDevelopment || isLocal ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  // Next.js extracts the nonce from the request CSP while dynamically
  // rendering framework and page scripts. The response header alone only
  // instructs the browser and leaves those generated scripts un-nonced.
  requestHeaders.set("Content-Security-Policy", policy);

  const pathname = request.nextUrl.pathname;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  const isReviewLogin = pathname === "/review/login";
  const isReviewRoute = pathname === "/review" || pathname.startsWith("/review/");
  if (isReviewRoute && !isReviewLogin && !hasSession) {
    const response = NextResponse.redirect(new URL("/review/login", request.url), 303);
    response.headers.set("Cache-Control", "no-store");
    return withContentSecurityPolicy(response, policy);
  }

  const isContentLogin = pathname === "/content/login";
  const isContentRoute = pathname === "/content" || pathname.startsWith("/content/");
  if (isContentRoute && !isContentLogin && !hasSession) {
    const response = NextResponse.redirect(new URL("/content/login", request.url), 303);
    response.headers.set("Cache-Control", "no-store");
    return withContentSecurityPolicy(response, policy);
  }

  const isOpsLogin = pathname === "/ops/login";
  const isOpsRoute = pathname === "/ops" || pathname.startsWith("/ops/");
  if (isOpsRoute && !isOpsLogin && !hasSession) {
    const acceptsHtml = request.headers.get("accept")?.includes("text/html") ?? false;
    const isServerAction = request.headers.has("next-action");
    if (acceptsHtml || isServerAction) {
      const response = NextResponse.redirect(new URL("/ops/login", request.url), 303);
      response.headers.set("Cache-Control", "no-store");
      return withContentSecurityPolicy(response, policy);
    }
    const response = NextResponse.json(
      { error: { code: "AUTH_REQUIRED", message: "Authentication required." } },
      { status: 401 },
    );
    response.headers.set("Cache-Control", "no-store");
    return withContentSecurityPolicy(response, policy);
  }

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  return withContentSecurityPolicy(response, policy);
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
