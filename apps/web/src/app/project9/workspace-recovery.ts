import type { AISelfCheckRecord } from "../actions";

export type WorkspaceDraft = { body: string; pendingSince: number | null };
export function workspaceKey(assignmentId: string, taskVersion: number, revision: number) {
  // Assignment UUID isolates accounts; revision isolates submitted/cancelled edits.
  return `journey:workspace:v1:${assignmentId}:${taskVersion}:${revision}`;
}
export function readWorkspace(storage: Pick<Storage, "getItem">, key: string): WorkspaceDraft | null {
  const raw = storage.getItem(key);
  if (raw === null) return null;
  try {
    const value = JSON.parse(raw);
    return typeof value?.body === "string" && value.body.length <= 100_000
      ? { body: value.body, pendingSince: typeof value.pendingSince === "number" && Number.isFinite(value.pendingSince) ? value.pendingSince : null }
      : null;
  } catch { return null; }
}
export function selfCheckRecovery(records: AISelfCheckRecord[], pendingSince: number | null, now = Date.now()) {
  const active = records.find(record => record.status === "RUNNING" || record.status === "SENDING");
  const newest = records[0];
  // Cover the short interval before the server has claimed a newly started check.
  // Expire an abandoned request marker; it must never lock the task indefinitely.
  const awaitingClaim = pendingSince !== null && now - pendingSince < 30_000
    && !records.some(record => Date.parse(record.createdAt) >= pendingSince - 1000);
  return { active, newest, busy: Boolean(active || awaitingClaim) };
}
