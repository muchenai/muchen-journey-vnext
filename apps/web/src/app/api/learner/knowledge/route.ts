import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store" };
const modules = new Set(["dashboard", "village", "academy", "guild"]);
const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);
const fail = (e: unknown) => NextResponse.json({ error: e instanceof ApiRequestError ? e.message : "知识库读取失败，请稍后重试。" },
  { status: e instanceof ApiRequestError ? e.status : 502, headers });

export async function GET(request: NextRequest) {
  const p = request.nextUrl.searchParams;
  const moduleId = p.get("module") || "";
  if (!modules.has(moduleId)) return NextResponse.json({ error: "知识库模块无效。" }, { status: 400, headers });
  let path = `/api/v1/me/knowledge/${moduleId}`;
  if (p.has("id") || p.has("position")) {
    const id = p.get("id"), position = p.get("position") || "";
    if (!uuid(id) || !/^\d{1,3}$/.test(position) || Number(position) >= 200)
      return NextResponse.json({ error: "文件参数无效。" }, { status: 400, headers });
    path += `/files/${id}/chunks/${Number(position)}`;
  }
  try { return NextResponse.json(await apiRequest(path, "LEARNER"), { headers }); }
  catch (error) { return fail(error); }
}

export async function POST(request: NextRequest) {
  let sameOrigin = false;
  try { const origin = new URL(request.headers.get("origin") || ""); sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol); } catch {}
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return NextResponse.json({ error: "请求来源不匹配。" }, { status: 403, headers });
  if (!request.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error: "请求格式不正确。" }, { status: 415, headers });
  try {
    const raw = await request.text();
    if (raw.length > 1000) return NextResponse.json({ error: "请求过长。" }, { status: 413, headers });
    let body;
    try { body = JSON.parse(raw); } catch { return NextResponse.json({ error: "请求格式不正确。" }, { status: 400, headers }); }
    if (!body || !modules.has(body.module) || !uuid(body.id) || typeof body.saved !== "boolean")
      return NextResponse.json({ error: "收藏参数无效。" }, { status: 400, headers });
    return NextResponse.json(await apiRequest(`/api/v1/me/knowledge/${body.module}/favorites/${body.id}`, "LEARNER", {
      method: "POST", body: JSON.stringify({ saved: body.saved }),
    }), { headers });
  } catch (error) { return fail(error); }
}
