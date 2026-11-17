import type { ReactNode } from "react";
import type { ExecutionTask } from "./ExecutionPages";

export type DashboardTaskEntry = {
  task: Pick<ExecutionTask, "id" | "title" | "description"> & { name?: string; completionMode?: "learning" | "assessment" | "checkin" };
  index: number;
  order?: number;
  status: "available" | "active" | "revision" | "pending" | "locked" | "completed" | "unavailable";
};

export const dashboardStatusLabels = {
  available: "正在进行中",
  active: "正在进行中",
  revision: "待修改",
  pending: "待审核",
  locked: "待解锁",
  completed: "已完成",
  unavailable: "暂不可用",
} as const;

export function prioritizeDashboardTasks(entries: DashboardTaskEntry[]) {
  const priority = { revision: 0, active: 1, available: 2, pending: 3, locked: 4, completed: 5, unavailable: 6 };
  return [...entries].sort((a, b) =>
    priority[a.status] - priority[b.status] || a.index - b.index);
}

export function DashboardTaskGrid({ entries, decoration, showDescription = false, onOpenTask }: {
  entries: DashboardTaskEntry[];
  decoration: ReactNode;
  showDescription?: boolean;
  onOpenTask?: (taskId: string) => void;
}) {
  return <section className="dashboard-task-board" tabIndex={0} aria-label={showDescription ? "匹配的探索营任务，按任务状态排序，可滚动查看" : "任务，优先展示待修改、正在进行中和待审核，可向下滚动查看全部任务"}>
    <div className="dashboard-task-tiles">
      {entries.map(({ task, index, order, status }) =>
        <button type="button" key={task.id}
          className="dashboard-task-tile figma-stroke figma-stroke-task"
          data-status={status} data-action={onOpenTask ? undefined : "open-task"} data-task-index={index} data-task-order={order}
          onClick={onOpenTask ? event => { event.stopPropagation(); if (status !== "locked" && status !== "unavailable") onOpenTask(task.id); } : undefined}
          disabled={onOpenTask && (status === "locked" || status === "unavailable") ? true : undefined}
          aria-disabled={status === "locked" || status === "unavailable"} aria-label={`${task.title}，${dashboardStatusLabels[status]}`}>
          {decoration}
          <span className="dashboard-tile-body">
            <span className="dashboard-tile-icon" aria-hidden="true">▤</span>
            <span className="dashboard-tile-copy">
              <strong>任务 · {task.title}</strong>
              <span className="dashboard-tile-status">{dashboardStatusLabels[status]}</span>
              <span>{showDescription ? task.description.trim() : status === "locked" ? "上一任务提交后解锁" : status === "unavailable" ? "该任务暂不可用" :
                status === "pending" ? "已提交，等待审核" :
                status === "revision" ? "审核未通过，请按评语修改后重新提交" :
                status === "completed" ? task.completionMode === "learning" ? "学习已完成，可回看材料" : task.completionMode === "checkin" ? "已确认签退并进入项目培训群" : "审核已通过，可回看任务" : task.description.trim()}</span>
            </span>
            <span className="dashboard-tile-clock" aria-hidden="true">◷</span>
          </span>
        </button>)}
    </div>
  </section>;
}
