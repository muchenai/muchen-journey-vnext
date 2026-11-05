import "server-only";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, STAFF_SESSION_COOKIE } from "@/lib/auth/cookies";

const MAX_COVER_BYTES = 1024 * 1024;
const uuid = /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

/** Reads a persisted course cover after the API rechecks this account's access. */
export async function proxyAcademyCover(request: NextRequest, courseId: string, role: "LEARNER" | "REVIEWER" | "OPERATOR"): Promise<Response> {
  const headers = new Headers({ "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", Vary: "Cookie" });
  const fail = (message: string, status: number) => request.method === "HEAD"
    ? new Response(null, { status, headers }) : NextResponse.json({ error: message }, { status, headers });
  if (!uuid.test(courseId) || !["GET", "HEAD"].includes(request.method)) return fail("课程参数无效。", 400);
  const source = new URL(request.url).searchParams.get("source");
  if (source !== null && !/^[a-f0-9]{64}$/i.test(source)) return fail("封面版本参数无效。", 400);
  const validator = request.headers.get("if-none-match");
  if (validator && validator !== "*" && !/^(?:W\/)?"[\x21\x23-\x7e]{1,128}"$/.test(validator)) return fail("封面缓存参数无效。", 400);
  const learner = role === "LEARNER";
  const cookieName = learner ? SESSION_COOKIE : STAFF_SESSION_COOKIE;
  const token = (await cookies()).get(cookieName)?.value;
  const fixture = process.env.ALLOW_FIXTURE_IDENTITY === "true" && ["local", "test"].includes(process.env.APP_ENV ?? "local");
  const upstreamHeaders = new Headers({ "X-Journey-Session-Scope": learner ? "learner" : "staff" });
  if (fixture && role === "REVIEWER") upstreamHeaders.set("X-Fixture-Role", role);
  else if (token) upstreamHeaders.set("Cookie", `${cookieName}=${token}`);
  else if (fixture) upstreamHeaders.set("X-Fixture-Role", role);
  else return fail("登录已失效，请重新登录。", 401);
  if (validator) upstreamHeaders.set("If-None-Match", validator);
  const url = new URL(`/api/v1/${learner ? "me" : "ops"}/academy/courses/${courseId}/cover`, process.env.API_INTERNAL_URL ?? "http://localhost:8000");
  if (source) url.searchParams.set("source", source);
  try {
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(30000)]);
    const init: RequestInit = {
      method: request.method, headers: upstreamHeaders, cache: "no-store", redirect: "error",
      signal,
    };
    let response = await fetch(url, init);
    // A publication job may already be extracting this source. Keep the original
    // artwork visible while it finishes, without repeating failed extractions.
    for (let attempt = 0; response.status === 425 && request.method === "GET" && attempt < 10; attempt++) {
      await response.body?.cancel();
      await new Promise(resolve => setTimeout(resolve, 2000));
      signal.throwIfAborted();
      response = await fetch(url, init);
    }
    if (response.status === 425) headers.set("Retry-After", "2");
    if (response.status !== 200 && response.status !== 304) {
      await response.body?.cancel();
      return fail("暂无可用封面。", [401, 403, 404, 425].includes(response.status) ? response.status : 502);
    }
    const etag = response.headers.get("etag");
    if (etag && /^(?:W\/)?"[\x21\x23-\x7e]{1,128}"$/.test(etag)) headers.set("ETag", etag);
    if (response.status === 304) {
      headers.set("Cache-Control", "private, no-cache");
      return new Response(null, { status: 304, headers });
    }
    if (response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "image/jpeg"
      || Number(response.headers.get("content-length")) > MAX_COVER_BYTES) {
      await response.body?.cancel();
      return fail("封面格式无效。", 502);
    }
    if (request.method === "HEAD") {
      headers.set("Content-Type", "image/jpeg");
      headers.set("Cache-Control", "private, no-cache");
      const size = response.headers.get("content-length");
      if (size && /^\d+$/.test(size)) headers.set("Content-Length", size);
      return new Response(null, { status: 200, headers });
    }
    const reader = response.body?.getReader();
    if (!reader) return fail("暂无可用封面。", 502);
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        size += part.value.byteLength;
        if (size > MAX_COVER_BYTES) { await reader.cancel(); return fail("封面大小无效。", 502); }
        chunks.push(part.value);
      }
    } finally { reader.releaseLock(); }
    const data = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
    if (size < 4 || data[0] !== 0xff || data[1] !== 0xd8 || data[2] !== 0xff || data[size - 2] !== 0xff || data[size - 1] !== 0xd9) return fail("封面格式无效。", 502);
    headers.set("Content-Type", "image/jpeg");
    headers.set("Content-Length", String(size));
    headers.set("Cache-Control", "private, no-cache");
    return new Response(data, { status: 200, headers });
  } catch { return fail("封面暂时无法读取。", 502); }
}
