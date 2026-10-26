import { previewStorage, type PreviewIdentity } from "./previewStorage";
import { readEvidence } from "./taskRecords";

type ActivityTask = { id: string; title: string };
export type TaskActivity = {
  id: string;
  actorId: PreviewIdentity;
  actorName: string;
  taskId: string;
  taskTitle: string;
  action: "completed" | "modified" | "resubmitted";
  createdAt: string;
};

function actorName(identity: PreviewIdentity) {
  return `${identity === "333" ? "账户" : "邀请码"} ${identity}`;
}

function storedActivity(): TaskActivity[] {
  try {
    const entries = JSON.parse(previewStorage.getItem("muchen-task-activity") || "[]");
    return Array.isArray(entries) ? entries.filter((entry): entry is TaskActivity =>
      entry && typeof entry.id === "string" && typeof entry.actorName === "string" &&
      ["111", "222", "333"].includes(entry.actorId) && typeof entry.taskId === "string" &&
      typeof entry.taskTitle === "string" && ["completed", "modified", "resubmitted"].includes(entry.action) &&
      Number.isFinite(Date.parse(entry.createdAt))) : [];
  } catch { return []; }
}

export function readTaskActivity(tasks: ActivityTask[], identity: PreviewIdentity | null): TaskActivity[] {
  if (!identity) return [];
  const entries = storedActivity();
  // Existing submissions retain their original timestamps without inventing past edits.
  for (const task of tasks) {
    const evidence = readEvidence(task.id);
    if (evidence && !entries.some(entry => entry.taskId === task.id && entry.action === "completed")) {
      entries.push({
        id: `submission-${task.id}-${evidence.submittedAt}`,
        actorId: identity, actorName: actorName(identity),
        taskId: task.id, taskTitle: task.title, action: "completed", createdAt: evidence.submittedAt,
      });
    }
  }
  return entries.reverse().sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
}

export function appendTaskActivity(
  task: ActivityTask,
  identity: PreviewIdentity | null,
  action: TaskActivity["action"],
) {
  if (!identity) return;
  // Persist any legacy completion before later edits or resubmissions replace its evidence.
  const entries = readTaskActivity([task], identity).reverse();
  entries.push({
    id: crypto.randomUUID(),
    actorId: identity, actorName: actorName(identity),
    taskId: task.id, taskTitle: task.title, action, createdAt: new Date().toISOString(),
  });
  previewStorage.setItem("muchen-task-activity", JSON.stringify(entries));
}
