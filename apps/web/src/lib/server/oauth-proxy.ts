import "server-only";

import { NextRequest, NextResponse } from "next/server";

type ApiErrorEnvelope = { error?: { code?: string } };

const SAFE_ERROR = /^[A-Z0-9_]{3,80}$/;

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

function safeErrorRedirect(request: NextRequest, code: string): NextResponse {
  const target = new URL("/", request.url);
  target.searchParams.set("auth_error", SAFE_ERROR.test(code) ? code : "IDENTITY_LOGIN_FAILED");
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
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
    return safeErrorRedirect(request, "IDENTITY_PROVIDER_UNAVAILABLE");
  }
  if (!response.ok || !payload.data) {
    return safeErrorRedirect(request, payload.error?.code ?? "IDENTITY_LOGIN_FAILED");
  }
  return { data: payload.data, response };
}

export function identityRedirect(
  location: URL | string,
  upstream: Response,
): NextResponse {
  const response = NextResponse.redirect(location, 303);
  appendSetCookies(upstream, response);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
