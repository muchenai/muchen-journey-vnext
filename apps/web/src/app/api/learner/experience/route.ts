import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

const headers = { "Cache-Control": "private, no-store" };
const fail = (error: string, status: number) => NextResponse.json({ error }, { status, headers });

export async function POST(request: NextRequest) {
  let origin: URL;
  try { origin = new URL(request.headers.get("origin") ?? ""); }
  catch { return fail("请求来源不匹配。", 403); }
  if (!["http:", "https:"].includes(origin.protocol) || origin.host !== request.headers.get("host")
      || request.headers.get("sec-fetch-site") === "cross-site") return fail("请求来源不匹配。", 403);
  if (!request.headers.get("content-type")?.startsWith("application/json")) return fail("请求格式不正确。", 415);
  const key = request.headers.get("Idempotency-Key");
  if (!key || !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(key)) return fail("兑换请求标识无效。", 400);
  if (Number(request.headers.get("content-length")) > 1000) return fail("请求过长。", 413);
  const raw = await request.text();
  if (raw.length > 1000) return fail("请求过长。", 413);
  let body;
  try { body = JSON.parse(raw); }
  catch { return fail("请求格式不正确。", 400); }
  if (!body || Object.keys(body).length !== 1 || !Number.isSafeInteger(body.points) || body.points < 1)
    return fail("请输入正整数商城积分。", 400);
  try {
    const receipt = await apiRequest("/api/v1/me/profile/exchange", "LEARNER", {
      method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ points: body.points }),
    });
    return NextResponse.json(receipt, { headers });
  } catch (error) {
    return fail(error instanceof ApiRequestError ? error.message : "兑换结果尚未确认，请重试。", error instanceof ApiRequestError ? error.status : 502);
  }
}
