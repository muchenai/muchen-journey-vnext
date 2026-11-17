import type { VillageTask } from "./useVillageTasks";

export const explorationStatusLabels: Record<string, string> = {
  available: "进行中",
  active: "进行中",
  locked: "待解锁",
  pending: "待审核",
  returned: "待修改",
  revision: "待修改",
  completed: "已完成",
  unavailable: "暂不可用",
};

export function canOpenExplorationTask(task: { status: string }) {
  return task.status !== "locked" && task.status !== "unavailable";
}

export function needsExplorationClaim(task: Pick<VillageTask, "status" | "claimed" | "assignmentId">) {
  return ["active", "available"].includes(task.status)
    && (task.status === "available" || task.claimed === false || task.assignmentId === null);
}
