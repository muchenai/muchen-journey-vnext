import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store" };
const reply = (body: unknown, status = 200) => NextResponse.json(body, { status, headers });
const fail = (error: unknown) => reply({ error: error instanceof ApiRequestError ? error.message : "公会晋级审核操作失败，请稍后重试。" }, error instanceof ApiRequestError ? error.status : 502);

export async function GET() {
  try { return reply(await apiRequest("/api/v1/review-admin/guild-requests", "REVIEWER")); }
  catch (error) { return fail(error); }
}

export async function POST(request: NextRequest) {
  let sameOrigin = false;
  try {
    const origin = new URL(request.headers.get("origin") || "");
    sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol);
  } catch { /* Missing or malformed origins are rejected. */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return reply({ error: "请求来源不匹配。" }, 403);
  if (!request.headers.get("content-type")?.startsWith("application/json")) return reply({ error: "请求格式不正确。" }, 415);
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 10000) return reply({ error: "提交内容过长。" }, 413);
    let body;
    try { body = JSON.parse(raw); } catch { return reply({ error: "请求格式不正确。" }, 400); }
    if (!body || Array.isArray(body) || typeof body.id !== "string" || !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(body.id) || !["approved", "returned"].includes(body.decision) || (body.reason !== undefined && typeof body.reason !== "string")) return reply({ error: "审核参数无效。" }, 400);
    const reason = (body.reason || "").trim();
    if (reason.length > 1000 || (body.decision === "returned" && !reason)) return reply({ error: "退回时请填写原因，最多 1000 个字。" }, 400);
    return reply(await apiRequest(`/api/v1/review-admin/guild-requests/${body.id}/review`, "REVIEWER", { method: "POST", body: JSON.stringify({ decision: body.decision, reason }) }));
  } catch (error) { return fail(error); }
}
