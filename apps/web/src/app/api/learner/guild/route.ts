import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store" };
const reply = (body: unknown, status = 200) => NextResponse.json(body, { status, headers });
const fail = (error: unknown) => reply({ error: error instanceof ApiRequestError ? error.message : "公会认证操作失败，请稍后重试。" }, error instanceof ApiRequestError ? error.status : 502);
const guildIds = new Set(["multilingual", "agent-trajectories", "code-reasoning", "quality-data", "multimodal", "model-evaluation", "dialect-speech", "functional"]);

export async function GET() {
  try { return reply(await apiRequest("/api/v1/me/guild", "LEARNER")); }
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
    if (Buffer.byteLength(raw) > 30000) return reply({ error: "提交内容过长。" }, 413);
    let body;
    try { body = JSON.parse(raw); } catch { return reply({ error: "请求格式不正确。" }, 400); }
    if (!body || Array.isArray(body) || !guildIds.has(body.guildId)) return reply({ error: "请选择有效的工会。" }, 400);
    let endpoint: string;
    let payload: Record<string, unknown> = { guildId: body.guildId };
    if (body.command === "join") {
      endpoint = "/api/v1/me/guild/join";
    } else {
      if (!["task", "apply"].includes(body.command) || !Number.isInteger(body.level) || ![1, 2, 3].includes(body.level)) return reply({ error: "请选择有效的认证阶段。" }, 400);
      payload.level = body.level;
      if (body.command === "apply") {
        if (!Number.isSafeInteger(body.expectedRevision) || body.expectedRevision < 1) return reply({ error: "请重新载入任务成果后再申请认证。" }, 400);
        payload.expectedRevision = body.expectedRevision;
        endpoint = "/api/v1/me/guild/requests";
      } else {
        if (typeof body.artifact !== "string" || body.artifact.length > 6000 || typeof body.submit !== "boolean" || !Array.isArray(body.checks) || body.checks.length > 3 || body.checks.some((check: unknown) => typeof check !== "string" || check.length > 200) || (body.expectedRevision !== undefined && (!Number.isInteger(body.expectedRevision) || body.expectedRevision < 0))) return reply({ error: "请检查任务成果和自查内容。" }, 400);
        endpoint = "/api/v1/me/guild/tasks";
        payload = { ...payload, artifact: body.artifact, checks: body.checks, submit: body.submit };
        if (body.expectedRevision !== undefined) payload.expectedRevision = body.expectedRevision;
      }
    }
    return reply(await apiRequest(endpoint, "LEARNER", { method: "POST", body: JSON.stringify(payload) }));
  } catch (error) { return fail(error); }
}
