import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";
import { proxyAcademyVideo } from "@/lib/server/academy-media";
import { proxyAcademyCover } from "@/lib/server/academy-cover";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ segments?: string[] }> };
const uuid = /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
const headers = { "Cache-Control": "private, no-store" };
const reply = (body: unknown, status = 200) => NextResponse.json(body, { status, headers });
const fail = (error: unknown) => reply({ ok: false, error: error instanceof ApiRequestError ? error.message : "学院连接失败，请稍后重试。" }, error instanceof ApiRequestError ? error.status : 502);

async function readLimited(request: NextRequest, limit: number): Promise<Uint8Array | null> {
  if (Number(request.headers.get("content-length")) > limit) return null;
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      size += part.value.byteLength;
      if (size > limit) { await reader.cancel(); return null; }
      chunks.push(part.value);
    }
  } finally { reader.releaseLock(); }
  const content = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { content.set(chunk, offset); offset += chunk.byteLength; }
  return content;
}

function allowed(parts: string[], method: string) {
  if (!parts.length) return method === "GET";
  if (parts.length === 1) return ["courses", "uploads"].includes(parts[0]) && method === "POST";
  if (!uuid.test(parts[1] || "")) return false;
  if (parts.length === 2) return (parts[0] === "courses" && method === "PATCH") || (parts[0] === "uploads" && method === "DELETE");
  if (parts.length === 3) return (parts[0] === "courses" && parts[2] === "visibility" && method === "POST")
    || (parts[0] === "shares" && parts[2] === "review" && method === "POST")
    || (parts[0] === "uploads" && parts[2] === "complete" && method === "POST")
    || (parts[0] === "courses" && ["video", "cover"].includes(parts[2]) && ["GET", "HEAD"].includes(method));
  return parts.length === 4 && parts[0] === "uploads" && parts[2] === "chunks" && /^\d{1,4}$/.test(parts[3]) && Number(parts[3]) < 1000 && method === "PUT";
}

async function handle(request: NextRequest, context: Context) {
  const parts = (await context.params).segments || [], method = request.method;
  if (!allowed(parts, method)) return reply({ ok: false, error: "学院请求参数无效。" }, 400);
  if (parts[2] === "video") return proxyAcademyVideo(request, parts[1], "REVIEWER");
  if (parts[2] === "cover") return proxyAcademyCover(request, parts[1], "REVIEWER");
  const write = !["GET", "HEAD"].includes(method);
  if (write) {
    let sameOrigin = false;
    try { const origin = new URL(request.headers.get("origin") || ""); sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol); } catch { /* Invalid origin. */ }
    if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return reply({ ok: false, error: "请求来源不匹配，请刷新重试。" }, 403);
  }
  try {
    const init: RequestInit = { method };
    if (method === "PUT") {
      if (!request.headers.get("content-type")?.startsWith("application/octet-stream")) return reply({ ok: false, error: "视频分片格式不正确。" }, 415);
      const content = await readLimited(request, 524288);
      if (!content?.byteLength) return reply({ ok: false, error: "视频分片大小不正确。" }, 413);
      init.body = content.buffer as ArrayBuffer; init.headers = { "Content-Type": "application/octet-stream" };
    } else if (write && method !== "DELETE") {
      if (!request.headers.get("content-type")?.startsWith("application/json")) return reply({ ok: false, error: "请求格式不正确。" }, 415);
      const content = await readLimited(request, 16000);
      if (!content) return reply({ ok: false, error: "课程信息过长。" }, 413);
      const raw = new TextDecoder().decode(content);
      let body;
      try { body = JSON.parse(raw); } catch { return reply({ ok: false, error: "请求格式不正确。" }, 400); }
      if (!body || Array.isArray(body) || typeof body !== "object") return reply({ ok: false, error: "请求格式不正确。" }, 400);
      init.body = JSON.stringify(body);
    }
    const data = await apiRequest(`/api/v1/ops/academy${parts.length ? '/' + parts.join('/') : ''}`, "REVIEWER", init);
    return reply({ ok: true, data });
  } catch (error) { return fail(error); }
}
export const GET = handle;
export const HEAD = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
