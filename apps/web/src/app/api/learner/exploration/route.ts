import { apiRequest, ApiRequestError } from "@/lib/server/api";
import { explorationMaterialResponse } from "@/lib/server/exploration-material-proxy";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store" };
const uuid = (id: unknown): id is string => typeof id === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(id);
function failure(error: unknown) {
  return Response.json({ error: error instanceof ApiRequestError ? error.message : "任务操作失败，请重试。" }, {
    status: error instanceof ApiRequestError ? error.status : 502, headers,
  });
}

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  const taskId = query.get("task");
  if (taskId && !uuid(taskId)) return Response.json({ error: "任务标识无效。" }, { status: 400, headers });
  const group = query.get("group");
  if (query.has("group") && (group !== "task" || !query.has("material"))) {
    return Response.json({ error: "材料分组参数无效。" }, { status: 400, headers });
  }
  const params = new URLSearchParams({ command: taskId ? "learnerTask" : "learnerSnapshot" });
  if (taskId) params.set("taskId", taskId);
  try {
    if (query.has("treasures")) {
      if (query.get("treasures") !== "1" || taskId || query.has("selfChecks") || query.has("material")) {
        return Response.json({ error: "宝藏参数无效。" }, { status: 400, headers });
      }
      params.set("command", "treasures");
    }
    if (query.has("selfChecks")) {
      if (!taskId || query.get("selfChecks") !== "1" || query.has("material")) {
        return Response.json({ error: "自测历史参数无效。" }, { status: 400, headers });
      }
      params.set("command", "selfCheckHistory");
    }
    if (query.has("material")) {
      const index = query.get("material") || "";
      if (!taskId || !/^\d{1,2}$/.test(index)) return Response.json({ error: "材料参数无效。" }, { status: 400, headers });
      params.set("command", "material");
      params.set("index", index);
      if (group === "task") params.set("group", group);
      const file = await apiRequest<{ id?: string; name: string; mime: string; data?: string }>(`/api/v1/me/exploration?${params}`, "LEARNER");
      if (file.id) return explorationMaterialResponse(request, file.id, "LEARNER");
      if (typeof file.data !== "string") return Response.json({ error: "材料不可用。" }, { status: 404, headers });
      const inline = query.get("inline") === "1" && /^(?:image\/(?:png|jpeg|gif|webp|avif|bmp|x-ms-bmp)|video\/(?:mp4|webm|ogg)|audio\/(?:mpeg|ogg))$/.test(file.mime);
      return new Response(Buffer.from(file.data, "base64"), { headers: {
        ...headers, "Content-Type": file.mime, "X-Content-Type-Options": "nosniff",
        "Content-Disposition": `${inline ? "inline" : "attachment"}; filename*=UTF-8''${encodeURIComponent(file.name)}`,
      } });
    }
    return Response.json(await apiRequest(`/api/v1/me/exploration?${params}`, "LEARNER"), { headers });
  } catch (error) { return failure(error); }
}

export async function POST(request: Request) {
  let sameOrigin = false;
  try {
    const origin = new URL(request.headers.get("origin") || "");
    sameOrigin = origin.host === request.headers.get("host") && ["http:", "https:"].includes(origin.protocol);
  } catch { /* Invalid origin. */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return Response.json({ error: "请求来源不匹配。" }, { status: 403, headers });
  if (!request.headers.get("content-type")?.startsWith("application/json")) return Response.json({ error: "请求格式不正确。" }, { status: 415, headers });
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 65536) return Response.json({ error: "提交内容过长。" }, { status: 413, headers });
    let body;
    try { body = JSON.parse(raw); } catch { return Response.json({ error: "请求格式不正确。" }, { status: 400, headers }); }
    if (!body || Array.isArray(body)) return Response.json({ error: "任务操作参数无效。" }, { status: 400, headers });
    const key = body.key ?? body.idempotencyKey;
    if (!uuid(key)) return Response.json({ error: "请求标识无效，请重新操作。" }, { status: 400, headers });
    const globalCommand = body.command === "unlockGraduation" || body.command === "ackTreasure";
    if (body.command === "ackTreasure" && !uuid(body.id)) return Response.json({ error: "宝藏标识无效。" }, { status: 400, headers });
    if (!globalCommand && (!uuid(body.taskId) || !["claim", "draft", "submit", "cancel", "selfCheck", "readMaterial", "completeLearning"].includes(body.command))) {
      return Response.json({ error: "任务操作参数无效。" }, { status: 400, headers });
    }
    const command: Record<string, unknown> = { command: body.command, key };
    if (body.command === "ackTreasure") command.id = body.id;
    if (!globalCommand) {
      command.taskId = body.taskId;
      command.revision = body.revision;
      command.versionId = body.versionId;
      command.answer = body.answer ?? body.body;
      if (body.command === "readMaterial") command.index = body.index;
      if (body.command === "completeLearning") command.checkinConfirmed = body.checkinConfirmed === true;
    }
    return Response.json(await apiRequest("/api/v1/me/exploration", "LEARNER", {
      method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(command),
    }), { headers });
  } catch (error) { return failure(error); }
}
