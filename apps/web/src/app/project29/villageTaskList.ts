import type { VillageTask } from "./useVillageTasks";

export type VillageTaskStatusFilter = "all" | "active" | "pending" | "returned" | "completed";

export const villageTaskStatusOptions: readonly { value: VillageTaskStatusFilter; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "active", label: "进行中" },
  { value: "pending", label: "待审核" },
  { value: "returned", label: "待修改" },
  { value: "completed", label: "已完成" },
];

export function filterVillageTaskStatus(tasks: readonly VillageTask[], status: VillageTaskStatusFilter): VillageTask[] {
  return tasks.filter(task => status === "all" || task.status === status);
}

const statusPriority = (status: VillageTask["status"]) => status === "available" ? 0 : status === "completed" ? 2 : 1;

export function sortVillageTasks(tasks: readonly VillageTask[], sort: string): VillageTask[] {
  return [...tasks].sort((a, b) => {
    const priority = statusPriority(a.status) - statusPriority(b.status);
    if (priority) return priority;
    if (sort === "duration") return a.minutes - b.minutes;
    if (sort === "reward") return b.experience - a.experience;
    return 0;
  });
}
