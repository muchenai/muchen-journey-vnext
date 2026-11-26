import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

const headers = { "Cache-Control": "private, no-store" };
const MAX_JSON_BYTES = 1_500_000;
const fail = (error: string, status: number) => NextResponse.json({ ok: false, error }, { status, headers });

async function readBody(request: NextRequest) {
  const reader = request.body?.getReader();
  if (!reader) return fail("请提供请求内容。", 400);
  const decoder = new TextDecoder();
  const parts: string[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_JSON_BYTES) {
        await reader.cancel();
        return fail("请求内容过大。", 413);
      }
      parts.push(decoder.decode(value, { stream: true }));
    }
  } finally {
    reader.releaseLock();
  }
  parts.push(decoder.decode());
  const raw = parts.join("");
  try {
    const body = JSON.parse(raw);
    if (body && typeof body === "object" && !Array.isArray(body)) return raw;
  } catch { /* Reject malformed JSON before forwarding. */ }
  return fail("请求格式不正确。", 400);
}

export async function forwardReviewManagement(request: NextRequest, path: string) {
  const init: RequestInit = { method: request.method };
  try {
    if (request.method === "POST") {
      let origin: URL;
      try { origin = new URL(request.headers.get("origin") || ""); }
      catch { return fail("请求来源不匹配，请刷新重试。", 403); }
      if (!["http:", "https:"].includes(origin.protocol) || origin.host !== request.headers.get("host") ||
          request.headers.get("sec-fetch-site") === "cross-site") return fail("请求来源不匹配，请刷新重试。", 403);
      if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") return fail("请求格式不正确。", 415);
      if (Number(request.headers.get("content-length")) > MAX_JSON_BYTES) return fail("请求内容过大。", 413);
      const body = await readBody(request);
      if (typeof body !== "string") return body;
      init.body = body;
    }
    const data = await apiRequest(path, "REVIEWER", init);
    return NextResponse.json({ ok: true, data }, { headers });
  } catch (error) {
    return error instanceof ApiRequestError ? fail(error.message, error.status) : fail("管理服务暂时无法连接，请重试。", 502);
  }
}
