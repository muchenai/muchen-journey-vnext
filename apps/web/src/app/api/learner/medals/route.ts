import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };
function fail(error: unknown) {
  return NextResponse.json({ error: error instanceof ApiRequestError ? error.message : "徽章数据读取失败，请重试。" },
    { status: error instanceof ApiRequestError ? error.status : 500, headers });
}
export async function GET() {
  try { return NextResponse.json(await apiRequest("/api/v1/me/novice/medals", "LEARNER"), { headers }); }
  catch (error) { return fail(error); }
}
export async function POST(request: NextRequest) {
  let sameOrigin = false;
  try { const origin = new URL(request.headers.get("origin") || ""); sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol); } catch { /* invalid origin */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return NextResponse.json({ error: "请求来源不匹配。" }, { status: 403, headers });
  if (!request.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error: "请求格式不正确。" }, { status: 415, headers });
  try {
    const raw = await request.text();
    if (raw.length > 1000) return NextResponse.json({ error: "请求过长。" }, { status: 413, headers });
    let body;
    try { body = JSON.parse(raw); } catch { return NextResponse.json({ error: "请求格式不正确。" }, { status: 400, headers }); }
    if (!body || typeof body.medalId !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(body.medalId) || !Number.isSafeInteger(body.revision) || body.revision < 1)
      return NextResponse.json({ error: "兑换参数无效。" }, { status: 400, headers });
    return NextResponse.json(await apiRequest(`/api/v1/me/novice/medals/${body.medalId}/redeem`, "LEARNER", {
      method: "POST", body: JSON.stringify({ expected_revision: body.revision }),
    }), { headers });
  } catch (error) { return fail(error); }
}
