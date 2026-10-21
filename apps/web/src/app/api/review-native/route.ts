import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { apiRequest, ApiRequestError } from "@/lib/server/api";
import { SESSION_COOKIE, CSRF_COOKIE } from "@/lib/auth/cookies";
import { loadAdmin, loadReview, saveAdminTask, archiveAdminTask, publishAdminTask, decideAdminReview, certifyMember, testAdminTask } from "@/app/review/admin-actions";
import type { AdminTask, Member } from "@/app/review/admin-types";

export const dynamic = "force-dynamic";
const reply = (body: unknown, status = 200) => {
  const result = body as { ok?: boolean; status?: number } | null;
  const responseStatus = result?.ok === false && result.status && [401, 403].includes(result.status) ? result.status : status;
  return NextResponse.json(body, { status: responseStatus, headers: { "Cache-Control": "no-store" } });
};
const uuid = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("review");
  if (id && !uuid(id)) return reply({ ok: false, error: "无效的审核记录。" }, 400);
  return reply(id ? await loadReview(id) : await loadAdmin());
}
export async function POST(request: NextRequest) {
  // This HTML client does not use Next server-action transport; enforce its
  // origin here, while apiRequest retains the existing backend CSRF checks.
  const origin = request.headers.get("origin");
  let sameOrigin = false;
  try { sameOrigin = !!origin && new URL(origin).host === request.headers.get("host") && ["http:", "https:"].includes(new URL(origin).protocol); } catch { /* Invalid origin. */ }
  if (!sameOrigin || request.headers.get("sec-fetch-site") === "cross-site") return reply({ ok: false, error: "请求来源不匹配，请刷新后重试。" }, 403);
  if (!request.headers.get("content-type")?.startsWith("application/json")) return reply({ ok: false, error: "请求格式不正确。" }, 415);
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 4_500_000) return reply({ ok: false, error: "附件过大，请改用文档链接。" }, 413);
    const body = JSON.parse(raw);
    if (!body || typeof body !== "object") return reply({ ok: false, error: "请求格式不正确。" }, 400);
    const { command, task, id, key, payload } = body;
    switch (command) {
      case "saveTask":
      case "archiveTask":
      case "publishTask":
        if (!uuid(task?.id) || !Number.isInteger(task.revision) || task.revision < 0) break;
        if (command === "saveTask") return reply(await saveAdminTask(task as AdminTask));
        if (command === "archiveTask") return reply(await archiveAdminTask(task as AdminTask));
        if (!uuid(payload?.reviewerId) || !uuid(key) || !Array.isArray(payload?.verified)) break;
        return reply(await publishAdminTask(task as AdminTask, payload.reviewerId, payload.verified, key));
      case "decide":
        if (!uuid(id) || !uuid(key) || !payload || !Number.isInteger(payload.expected_revision)) break;
        return reply(await decideAdminReview(id, payload, key));
      case "certify":
        if (!uuid(payload?.member?.id) || !Number.isInteger(payload.member.revision)) break;
        return reply(await certifyMember(payload.member as Member, payload.domain, payload.level));
      case "sandbox":
        if (!task || typeof payload?.answer !== "string" || payload.answer.length > 30000) break;
        return reply(await testAdminTask(task as AdminTask, payload.answer));
      case "logout": {
        try { await apiRequest("/api/v1/session/logout", "LEARNER", { method: "POST" }); }
        catch (error) { if (!(error instanceof ApiRequestError && error.status === 401 && error.code === "UNAUTHENTICATED")) throw error; }
        const jar = await cookies(); jar.delete(SESSION_COOKIE); jar.delete(CSRF_COOKIE);
        return reply({ ok: true, data: null });
      }
    }
    return reply({ ok: false, error: "请求参数不正确。" }, 400);
  } catch {
    return reply({ ok: false, error: "操作未完成，请刷新后重试。" }, 500);
  }
}
