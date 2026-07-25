import { NextRequest, NextResponse } from "next/server";

import { identityRedirect, postIdentityApi } from "@/lib/server/oauth-proxy";

export const dynamic = "force-dynamic";

const OAUTH_VALUE = /^[A-Za-z0-9._~-]{1,512}$/;
const SAFE_ENTRIES = new Set(["/review", "/ops"]);

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get("code") ?? "";
  const state = request.nextUrl.searchParams.get("state") ?? "";
  if (!OAUTH_VALUE.test(code) || state.length < 32 || !OAUTH_VALUE.test(state)) {
    return NextResponse.redirect(new URL("/?auth_error=OAUTH_CALLBACK_INVALID", request.url), 303);
  }
  const result = await postIdentityApi<{ safe_entry: string }>(
    request,
    "/api/v1/auth/feishu/callback",
    { code, state },
  );
  if (result instanceof NextResponse) return result;
  if (!SAFE_ENTRIES.has(result.data.safe_entry)) {
    return NextResponse.redirect(
      new URL("/?auth_error=IDENTITY_PROVIDER_INVALID", request.url),
      303,
    );
  }
  return identityRedirect(new URL(result.data.safe_entry, request.url), result.response);
}
