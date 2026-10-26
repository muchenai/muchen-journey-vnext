import { previewStorage } from "./previewStorage";

export type TaskEvidence = {
  record: string;
  submittedAt: string;
  status: "submitted" | "pending-review" | "reviewed";
};
export type TaskFeedback = {
  id: string;
  source: "ai" | "mentor";
  message: string;
  createdAt: string;
  submittedAt: string;
  score?: number;
  demo?: boolean;
};

export function readEvidence(taskId: string): TaskEvidence | null {
  try {
    const value = JSON.parse(previewStorage.getItem(`muchen-task-${taskId}-evidence`) || "null");
    if (!value || typeof value.record !== "string" || !Number.isFinite(Date.parse(value.submittedAt))) return null;
    return { ...value, status: value.status === "reviewed" ? "reviewed" : "submitted" };
  } catch { return null; }
}

export function readFeedback(taskId: string): TaskFeedback[] {
  try {
    const value = JSON.parse(previewStorage.getItem(`muchen-task-${taskId}-feedback`) || "[]");
    return Array.isArray(value) ? value.filter((item): item is TaskFeedback =>
      item && typeof item.id === "string" && (item.source === "ai" || item.source === "mentor") &&
      typeof item.message === "string" && Number.isFinite(Date.parse(item.createdAt))) : [];
  } catch { return []; }
}

export function simulateFeedback(taskId: string, source: TaskFeedback["source"]) {
  const evidence = readEvidence(taskId);
  if (!evidence) return;
  const feedback = readFeedback(taskId);
  if (feedback.some(item => item.source === source && item.submittedAt === evidence.submittedAt)) return;
  const createdAt = new Date().toISOString();
  feedback.push({
    id: `${source}-${createdAt}`,
    source, createdAt, submittedAt: evidence.submittedAt, demo: true,
    ...(source === "ai" ? { score: 85 } : {}),
    message: source === "ai"
      ? "本地模拟评分：85 分。建议补充判断依据与下一步行动；此分数不是实际 AI 评测结果。"
      : "本地模拟导师审核通过。建议保留任务证据，并将本次学习结论应用到下一任务；此内容不是真实导师反馈。",
  });
  previewStorage.setItem(`muchen-task-${taskId}-feedback`, JSON.stringify(feedback));
  if (source === "mentor") {
    previewStorage.setItem(`muchen-task-${taskId}-evidence`, JSON.stringify({ ...evidence, status: "reviewed" }));
  }
}

export function learningStreak(submissionDates: string[], now = new Date()) {
  const dayKey = (date: Date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  const days = new Set(submissionDates.map(date => dayKey(new Date(date))));
  const cursor = new Date(now);
  if (!days.has(dayKey(cursor))) cursor.setDate(cursor.getDate() - 1);
  let streak = 0;
  while (days.has(dayKey(cursor))) { streak++; cursor.setDate(cursor.getDate() - 1); }
  return streak;
}
