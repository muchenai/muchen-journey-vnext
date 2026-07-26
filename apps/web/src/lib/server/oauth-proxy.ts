import "server-only";

import { NextRequest, NextResponse } from "next/server";

type ApiErrorEnvelope = { error?: { code?: string } };

const SAFE_ERROR = /^[A-Z0-9_]{3,80}$/;
const SAFE_SAME_ORIGIN_LOCATION = /^\/(?!\/)[^\r\n]*$/;

function apiBaseUrl(): string {
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

function forwardedFor(request: NextRequest): string | null {
  return request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
}

function appendSetCookies(source: Response, target: NextResponse): void {
  const headers = source.headers as Headers & { getSetCookie?: () => string[] };
  const combined = source.headers.get("set-cookie");
  const values = headers.getSetCookie?.() ?? (combined ? [combined] : []);
  for (const value of values) target.headers.append("Set-Cookie", value);
}

function safeErrorRedirect(code: string): NextResponse {
  const safeCode = SAFE_ERROR.test(code) ? code : "IDENTITY_LOGIN_FAILED";
  return sameOriginIdentityRedirect(`/?auth_error=${safeCode}`);
}

export async function postIdentityApi<T>(
  request: NextRequest,
  path: string,
  body: Record<string, string>,
): Promise<{ data: T; response: Response } | NextResponse> {
  const headers = new Headers({
    Accept: "application/json",
    "Content-Type": "application/json",
  });
  const clientChain = forwardedFor(request);
  if (clientChain) headers.set("X-Forwarded-For", clientChain);
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("Cookie", cookie);
  const response = await fetch(new URL(path, apiBaseUrl()), {
    method: "POST",
    cache: "no-store",
    headers,
    body: JSON.stringify(body),
  });
  let payload: { data?: T } & ApiErrorEnvelope;
  try {
    payload = (await response.json()) as { data?: T } & ApiErrorEnvelope;
  } catch {
    return safeErrorRedirect("IDENTITY_PROVIDER_UNAVAILABLE");
  }
  if (!response.ok || !payload.data) {
    return safeErrorRedirect(payload.error?.code ?? "IDENTITY_LOGIN_FAILED");
  }
  return { data: payload.data, response };
}

function secureRedirect(response: NextResponse, upstream?: Response): NextResponse {
  if (upstream) appendSetCookies(upstream, response);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export function sameOriginIdentityRedirect(
  location: string,
  upstream?: Response,
): NextResponse {
  if (!SAFE_SAME_ORIGIN_LOCATION.test(location)) {
    throw new Error("same-origin identity redirect must be a root-relative path");
  }
  return secureRedirect(
    new NextResponse(null, { status: 303, headers: { Location: location } }),
    upstream,
  );
}

export function identityRedirect(location: URL, upstream: Response): NextResponse {
  const response = NextResponse.redirect(location, 303);
  return secureRedirect(response, upstream);
}
