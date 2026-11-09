import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const offset = params.get("offset") ?? "0";
  const limit = params.get("limit") ?? "20";
  if (!/^\d+$/.test(offset) || !/^\d+$/.test(limit)
    || !Number.isSafeInteger(Number(offset)) || Number(offset) > 2147483647 || Number(limit) < 1 || Number(limit) > 100) {
    return NextResponse.json({ error: "成长明细分页无效，请重新加载。" }, { status: 400, headers });
  }
  try {
    const data = await apiRequest(`/api/v1/me/novice/growth?offset=${Number(offset)}&limit=${Number(limit)}`, "LEARNER");
    return NextResponse.json(data, { headers });
  } catch (error) {
    return NextResponse.json({ error: error instanceof ApiRequestError ? error.message : "成长明细读取失败，请重试。" }, {
      status: error instanceof ApiRequestError ? error.status : 500, headers,
    });
  }
}
