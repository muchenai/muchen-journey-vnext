import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET(_request: NextRequest): NextResponse {
  const fixtureIdentityAllowed =
    process.env.APP_ENV === "local" &&
    process.env.ALLOW_FIXTURE_IDENTITY === "true";

  if (!fixtureIdentityAllowed) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const response = new NextResponse(null, {
    status: 303,
    headers: { Location: "/review" },
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
