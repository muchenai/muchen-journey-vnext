import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic = "force-dynamic";
const uuid = (s: unknown): s is string => typeof s === "string" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(s);
function fail(error: unknown) {
  return NextResponse.json({ error: error instanceof ApiRequestError ? error.message : "操作未完成，请重试。" },
    { status: error instanceof ApiRequestError ? error.status : 500, headers: { "Cache-Control":"no-store" } });
}
export async function GET(request: NextRequest) {
  try {
    const task = request.nextUrl.searchParams.get("task");
    const material = request.nextUrl.searchParams.get("material");
    if (task && !uuid(task)) return NextResponse.json({ error:"任务参数无效。" }, { status:400 });
    if (material !== null) {
      if (!task || !/^\d{1,2}$/.test(material)) return NextResponse.json({ error:"文件参数无效。" }, { status:400 });
      const data = await apiRequest<{ name:string; mime:string; data:string }>(`/api/v1/me/novice/tasks/${task}/materials/${material}`, "LEARNER");
      return new NextResponse(Buffer.from(data.data, "base64"), { headers:{
        "Content-Type":data.mime, "Content-Disposition":`attachment; filename*=UTF-8''${encodeURIComponent(data.name)}`,
        "X-Content-Type-Options":"nosniff", "Cache-Control":"no-store" } });
    }
    const data = await apiRequest(`/api/v1/me/novice/tasks${task ? `/${task}` : ""}`, "LEARNER");
    return NextResponse.json(data, { headers:{ "Cache-Control":"no-store" } });
  } catch (error) { return fail(error); }
}
export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  let sameOrigin = false;
  try { sameOrigin = !!origin && new URL(origin).host === request.headers.get("host") && ["http:","https:"].includes(new URL(origin).protocol); } catch { /* invalid */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return NextResponse.json({ error:"请求来源不匹配。" }, { status:403 });
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error:"请求格式不正确。" }, { status:415 });
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 50000) return NextResponse.json({ error:"内容过长。" }, { status:413 });
    let body;
    try { body = JSON.parse(raw); } catch { return NextResponse.json({ error:"请求格式不正确。" }, { status:400 }); }
    if (!body || Array.isArray(body) || !uuid(body.taskId) || !uuid(body.key) || !["claim","draft","submit","cancel"].includes(body.command)) return NextResponse.json({ error:"请求参数无效。" }, { status:400 });
    if (body.command === "claim") {
      if (!uuid(body.versionId)) return NextResponse.json({ error:"任务版本无效。" }, { status:400 });
      if (body.revision != null && (!Number.isSafeInteger(body.revision) || body.revision < 1)) return NextResponse.json({ error:"任务状态已变化，请重新读取。" }, { status:400 });
      await apiRequest(`/api/v1/me/novice/tasks/${body.taskId}/claim`, "LEARNER", { method:"POST",
        headers:{"Idempotency-Key":body.key}, body:JSON.stringify({ version_id:body.versionId, ...(body.revision != null ? { expected_revision:body.revision } : {}) }) });
    } else if (body.command === "cancel") {
      if (!Number.isSafeInteger(body.revision) || body.revision < 1) return NextResponse.json({ error:"任务状态已变化，请重新读取。" }, { status:400 });
      await apiRequest(`/api/v1/me/novice/tasks/${body.taskId}/cancel`, "LEARNER", {
        method:"POST", headers:{"Idempotency-Key":body.key}, body:JSON.stringify({expected_revision:body.revision}) });
    } else {
      // Resolve the learner-owned assignment on the server, never trust a client assignment ID.
      const task = await apiRequest<{ assignmentId:string|null }>(`/api/v1/me/novice/tasks/${body.taskId}`, "LEARNER");
      if (!task.assignmentId || !Number.isInteger(body.revision) || typeof body.answer !== "string") return NextResponse.json({ error:"请先领取任务。" }, { status:400 });
      await apiRequest(`/api/v1/me/assignments/${task.assignmentId}/${body.command === "draft" ? "draft" : "submissions"}`, "LEARNER", {
        method:body.command === "draft" ? "PUT" : "POST", headers:{"Idempotency-Key":body.key},
        body:JSON.stringify({expected_revision:body.revision, body:body.answer, attachment_ids:[]}) });
    }
    return NextResponse.json(await apiRequest(`/api/v1/me/novice/tasks/${body.taskId}`, "LEARNER"), {headers:{"Cache-Control":"no-store"}});
  } catch (error) { return fail(error); }
}
