import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store" };
const maxBytes = 100 * 1024 * 1024;

export async function POST(request: Request) {
  let sameOrigin = false;
  try {
    const origin = new URL(request.headers.get("origin") || "");
    sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol);
  } catch { /* Invalid origin. */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") {
    return Response.json({ ok: false, error: "请求来源不匹配。", status: 403 }, { status: 403, headers });
  }
  const size = request.headers.get("content-length");
  if (size && (!/^\d+$/.test(size) || Number(size) > maxBytes)) {
    return Response.json({ ok: false, error: "单个文件不能超过 100 MB。", status: 413 }, { status: 413, headers });
  }
  const query = new URL(request.url).searchParams;
  const name = query.get("name") || "";
  const type = query.get("type") || "file";
  if (!name.trim() || name.length > 240 || !["file", "image"].includes(type) || !request.body) {
    return Response.json({ ok: false, error: "文件名称或类型无效。", status: 400 }, { status: 400, headers });
  }
  let received = 0;
  const limited = request.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      received += chunk.byteLength;
      if (received > maxBytes) throw new Error("MATERIAL_TOO_LARGE");
      controller.enqueue(chunk);
    },
  }));
  try {
    const init = {
      method: "POST", headers: { "Content-Type": request.headers.get("content-type") || "application/octet-stream" },
      body: limited, duplex: "half", redirect: "error", signal: request.signal,
    } as RequestInit & { duplex: "half" };
    const params = new URLSearchParams({ name, type });
    const data = await apiRequest(`/api/v1/review-admin/exploration/materials?${params}`, "REVIEWER", init);
    return Response.json({ ok: true, data }, { headers });
  } catch (error) {
    const tooLarge = received > maxBytes;
    const status = tooLarge ? 413 : error instanceof ApiRequestError ? error.status : 502;
    const message = tooLarge ? "单个文件不能超过 100 MB。" : error instanceof ApiRequestError ? error.message : "文件上传失败，请重试。";
    return Response.json({ ok: false, error: message, status }, { status, headers });
  }
}
