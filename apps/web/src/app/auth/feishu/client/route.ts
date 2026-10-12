import { NextRequest, NextResponse } from "next/server";
import { appendSetCookies, postIdentityApi } from "@/lib/server/oauth-proxy";

export const dynamic = "force-dynamic";
const VALUE = /^[A-Za-z0-9._~-]{1,512}$/;

function json(body: Record<string, unknown>, status = 200, upstream?: Response) {
  const response = NextResponse.json(body, { status });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  if (upstream) appendSetCookies(upstream, response);
  return response;
}

function apiError(response: NextResponse) {
  const location = response.headers.get("location") ?? "/";
  const code = new URL(location, "https://journey.invalid").searchParams.get("auth_error");
  return json({ error: code ?? "IDENTITY_PROVIDER_UNAVAILABLE" }, 400);
}

export async function POST(request: NextRequest) {
  // JSON + a custom header prevent cross-origin form submissions. Check the
  // browser origin too; never expose provider credentials or accept identities.
  const origin = request.headers.get("origin");
  let sameOrigin = false;
  try {
    const parsed = new URL(origin ?? "");
    sameOrigin = ["http:", "https:"].includes(parsed.protocol)
      && parsed.host === request.headers.get("host");
  } catch { /* rejected below */ }
  if (!sameOrigin || request.headers.get("x-journey-client-login") !== "1"
    || request.headers.get("content-type")?.split(";")[0] !== "application/json") {
    return json({ error: "FORBIDDEN" }, 403);
  }
  const raw = await request.text();
  if (raw.length > 2048) return json({ error: "VALIDATION_FAILED" }, 400);
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error();
  } catch { return json({ error: "VALIDATION_FAILED" }, 400); }

  try {
    if (body.step === "start") {
      const result = await postIdentityApi<{ authorization_url: string }>(request,
        "/api/v1/auth/feishu/start", { return_to: "/app" });
      if (result instanceof NextResponse) return apiError(result);
      const url = new URL(result.data.authorization_url);
      const appId = url.searchParams.get("client_id");
      const state = url.searchParams.get("state");
      if (url.origin !== "https://accounts.feishu.cn" || !appId?.match(/^cli_[A-Za-z0-9]+$/)
        || !state || state.length < 32 || !VALUE.test(state)) {
        return json({ error: "IDENTITY_PROVIDER_INVALID" }, 502);
      }
      return json({ appId, state }, 200, result.response);
    }
    if (body.step !== "complete" || typeof body.code !== "string" || !VALUE.test(body.code)
      || typeof body.state !== "string" || body.state.length < 32 || body.state.length > 256
      || !VALUE.test(body.state)) return json({ error: "VALIDATION_FAILED" }, 400);
    const result = await postIdentityApi<{ safe_entry: string }>(request,
      "/api/v1/auth/feishu/callback", {
        code: body.code, state: body.state, authorization_method: "client",
      });
    if (result instanceof NextResponse) return apiError(result);
    if (result.data.safe_entry !== "/app") return json({ error: "IDENTITY_PROVIDER_INVALID" }, 502);
    return json({ entry: "/app" }, 200, result.response);
  } catch {
    return json({ error: "IDENTITY_PROVIDER_UNAVAILABLE" }, 502);
  }
}
