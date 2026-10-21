"use server";
import { apiRequest, ApiRequestError, type ReviewDetail } from "@/lib/server/api";
import type { AdminState, AdminReview, AdminTask, Member, Result } from "./admin-types";
async function safely<T>(work: () => Promise<T>): Promise<Result<T>> {
 try { return { ok: true, data: await work() }; }
 catch (error) { return { ok: false, error: error instanceof ApiRequestError ? error.message : "连接暂时失败，请重试。",
  ...(error instanceof ApiRequestError ? { status: error.status, code: error.code } : {}) }; }
}
export async function loadAdmin(): Promise<Result<AdminState>> {
 return safely(async () => {
  const [reviews, tasks, members] = await Promise.all([
   apiRequest<{ items: AdminReview[]; actor: AdminState["actor"] }>("/api/v1/review-admin/reviews", "REVIEWER"),
   apiRequest<{ items: AdminTask[] }>("/api/v1/review-admin/tasks", "REVIEWER"),
   apiRequest<{ items: Member[]; actor_id: string }>("/api/v1/review-admin/members", "OPERATOR").catch(error => {
    if (error instanceof ApiRequestError && error.status === 403) return null;
    throw error;
   }),
  ]);
  return { reviews: reviews.items, tasks: tasks.items, actor: reviews.actor, members: members?.items ?? [], operatorId: members?.actor_id ?? null };
 });
}
export async function loadReview(id: string): Promise<Result<ReviewDetail>> {
 return safely(() => apiRequest<ReviewDetail>(`/api/v1/review-admin/reviews/${encodeURIComponent(id)}`, "REVIEWER"));
}
export async function saveAdminTask(task: AdminTask): Promise<Result<AdminTask>> {
 return safely(() => apiRequest<AdminTask>(`/api/v1/review-admin/tasks/${encodeURIComponent(task.id)}`, "OPERATOR", {
  method: "PUT", body: JSON.stringify({ id: task.id, expected_revision: task.revision, content: task }),
 }));
}
export async function publishAdminTask(task: AdminTask, reviewerId: string, verified: string[], key: string): Promise<Result<AdminTask>> {
 return safely(() => apiRequest<AdminTask>(`/api/v1/review-admin/tasks/${encodeURIComponent(task.id)}/publish`, "OPERATOR", {
  method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ expected_revision: task.revision, reviewed_by: reviewerId, verified_material_urls: verified }),
 }));
}
export async function archiveAdminTask(task: AdminTask): Promise<Result<AdminTask>> {
 return safely(() => apiRequest<AdminTask>(`/api/v1/review-admin/tasks/${encodeURIComponent(task.id)}/archive`, "OPERATOR", {
  method: "POST", body: JSON.stringify({ expected_revision: task.revision, archived: task.status !== "archived" }),
 }));
}
export async function decideAdminReview(id: string, command: { expected_revision: number; decision: string; feedback: string; score: number | null; reasons: string[];
 rubric_evaluations?: { dimension_key: string; rating: string; feedback: string; score?: number }[] }, key: string): Promise<Result<unknown>> {
 return safely(() => apiRequest(`/api/v1/review-admin/reviews/${encodeURIComponent(id)}/decision`, "REVIEWER", {
  method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(command),
 }));
}
export async function certifyMember(member: Member, domain: string, level: string): Promise<Result<unknown>> {
 return safely(() => apiRequest(`/api/v1/review-admin/members/${encodeURIComponent(member.id)}/certification`, "OPERATOR", {
  method: "PUT", body: JSON.stringify({ expected_revision: member.revision, domain, level }),
 }));
}
export async function testAdminTask(task: AdminTask, answer: string): Promise<Result<{ result: string; model: string }>> {
 return safely(() => apiRequest<{ result: string; model: string }>("/api/v1/review-admin/sandbox", "OPERATOR", {
  method: "POST", body: JSON.stringify({ task, answer }),
 }));
}
