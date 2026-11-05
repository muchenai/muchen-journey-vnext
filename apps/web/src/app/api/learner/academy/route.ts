import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store" };
const uuid = (id: unknown): id is string => typeof id === "string" && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(id);
const fail = (error: unknown) => NextResponse.json({ error: error instanceof ApiRequestError ? error.message : "学院操作失败，请稍后重试。" }, { status: error instanceof ApiRequestError ? error.status : 502, headers });

export async function GET() {
  try { return NextResponse.json(await apiRequest("/api/v1/me/academy", "LEARNER"), { headers }); }
  catch (error) { return fail(error); }
}

export async function POST(request: NextRequest) {
  let sameOrigin = false;
  try { const origin = new URL(request.headers.get("origin") || ""); sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol); } catch {}
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return NextResponse.json({ error: "请求来源不匹配。" }, { status: 403, headers });
  if (!request.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error: "请求格式不正确。" }, { status: 415, headers });
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 20000) return NextResponse.json({ error: "提交内容过长。" }, { status: 413, headers });
    let body;
    try { body = JSON.parse(raw); } catch { return NextResponse.json({ error: "请求格式不正确。" }, { status: 400, headers }); }
    if (!body || typeof body !== "object") return NextResponse.json({ error: "请求参数无效。" }, { status: 400, headers });
    let path = "", payload: Record<string, unknown> = {}, method = "POST";
    if (body.command === "favorite" && uuid(body.id) && typeof body.saved === "boolean") {
      path = `/api/v1/me/academy/courses/${body.id}/favorite`; payload = { saved: body.saved };
    } else if (body.command === "progress" && uuid(body.id) && typeof body.seconds === "number" && typeof body.duration === "number" && Number.isFinite(body.seconds) && Number.isFinite(body.duration) && body.seconds >= 0 && body.duration >= 0 && (body.completed === undefined || typeof body.completed === "boolean")) {
      if (body.revision !== undefined && !Number.isInteger(body.revision)) return NextResponse.json({ error: "课程版本参数无效。" }, { status: 400, headers });
      path = `/api/v1/me/academy/courses/${body.id}/progress`; payload = { seconds: body.seconds, duration: body.duration, ...(body.completed === undefined ? {} : { completed: body.completed }), ...(body.revision === undefined ? {} : { expected_revision: body.revision }) };
    } else if (["share", "resubmit"].includes(body.command) && typeof body.title === "string" && typeof body.summary === "string" && typeof body.url === "string" && typeof body.minutes === "number" && Array.isArray(body.tags)) {
      payload = { title: body.title, summary: body.summary, url: body.url, minutes: body.minutes, tags: body.tags };
      if (body.command === "share" && (body.id === undefined || uuid(body.id))) { path = "/api/v1/me/academy/shares"; if (body.id) payload.id = body.id; }
      else if (uuid(body.id) && Number.isInteger(body.revision)) { path = `/api/v1/me/academy/shares/${body.id}`; method = "PATCH"; payload.expected_revision = body.revision; }
    }
    if (!path) return NextResponse.json({ error: "学院操作参数无效。" }, { status: 400, headers });
    return NextResponse.json(await apiRequest(path, "LEARNER", { method, body: JSON.stringify(payload) }), { headers });
  } catch (error) { return fail(error); }
}
