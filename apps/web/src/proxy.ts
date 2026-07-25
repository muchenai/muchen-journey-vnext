import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/cookies";

function withContentSecurityPolicy(response: NextResponse, policy: string) {
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDevelopment = process.env.NODE_ENV === "development";
  const developmentEval = isDevelopment ? " 'unsafe-eval'" : "";
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${developmentEval}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDevelopment ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  // Next.js extracts the nonce from the request CSP while dynamically
  // rendering framework and page scripts. The response header alone only
  // instructs the browser and leaves those generated scripts un-nonced.
  requestHeaders.set("Content-Security-Policy", policy);

  const isOpsRoute =
    request.nextUrl.pathname === "/ops" || request.nextUrl.pathname.startsWith("/ops/");
  if (isOpsRoute && !request.cookies.get(SESSION_COOKIE)?.value) {
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
