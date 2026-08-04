import { NextRequest, NextResponse } from "next/server";

import {
  identityRedirect,
  postIdentityApi,
  sameOriginIdentityRedirect,
} from "@/lib/server/oauth-proxy";

export const dynamic = "force-dynamic";

const SAFE_RETURNS = new Set(["/review", "/ops", "/content"]);
const LINK_TOKEN = /^[A-Za-z0-9_-]{32,256}$/;

export async function GET(request: NextRequest): Promise<NextResponse> {
  const returnTo = request.nextUrl.searchParams.get("return_to") ?? "";
  const rawLinkToken = request.nextUrl.searchParams.get("link_token");
  if (!SAFE_RETURNS.has(returnTo) || (rawLinkToken && !LINK_TOKEN.test(rawLinkToken))) {
    return sameOriginIdentityRedirect("/?auth_error=VALIDATION_FAILED");
  }
  const result = await postIdentityApi<{ authorization_url: string }>(
    request,
    "/api/v1/auth/feishu/start",
    {
      return_to: returnTo,
      ...(rawLinkToken ? { link_token: rawLinkToken } : {}),
    },
  );
  if (result instanceof NextResponse) return result;
  const authorizationUrl = new URL(result.data.authorization_url);
  if (authorizationUrl.protocol !== "https:" || authorizationUrl.hostname !== "accounts.feishu.cn") {
    return sameOriginIdentityRedirect("/?auth_error=IDENTITY_PROVIDER_INVALID");
  }
  return identityRedirect(authorizationUrl, result.response);
}
