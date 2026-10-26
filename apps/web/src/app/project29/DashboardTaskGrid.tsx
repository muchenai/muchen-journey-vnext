import type { ReactNode } from "react";
import type { ExecutionTask } from "./ExecutionPages";

export type DashboardTaskEntry = {
  task: ExecutionTask;
  index: number;
  status: "active" | "revision" | "pending" | "locked" | "completed";
};

export const dashboardStatusLabels = {
  active: "正在进行中",
  revision: "待修改",
  pending: "待审核",
  locked: "待解锁",
  completed: "已完成",
} as const;

export function prioritizeDashboardTasks(entries: DashboardTaskEntry[]) {
  const priority = { revision: 0, active: 1, pending: 2, locked: 3, completed: 4 };
  return [...entries].sort((a, b) =>
    priority[a.status] - priority[b.status] || a.index - b.index);
}

export function DashboardTaskGrid({ entries, decoration }: {
  entries: DashboardTaskEntry[];
  decoration: ReactNode;
}) {
  return <section className="dashboard-task-board" tabIndex={0} aria-label="任务，优先展示待修改、正在进行中和待审核，可向下滚动查看全部任务">
    <div className="dashboard-task-tiles">
      {entries.map(({ task, index, status }) =>
        <button type="button" key={task.id}
          className="dashboard-task-tile figma-stroke figma-stroke-task"
          data-status={status} data-action="open-task" data-task-index={index}
          aria-disabled={status === "locked"} aria-label={`${task.title}，${dashboardStatusLabels[status]}`}>
          {decoration}
          <span className="dashboard-tile-body">
            <span className="dashboard-tile-icon" aria-hidden="true">▤</span>
            <span className="dashboard-tile-copy">
              <strong>任务 · {task.title}</strong>
              <span className="dashboard-tile-status">{dashboardStatusLabels[status]}</span>
              <span>{status === "locked" ? "上一任务提交后解锁" :
                status === "pending" ? "已提交，等待审核" :
                status === "revision" ? "审核未通过，请按评语修改后重新提交" :
                status === "completed" ? "审核已通过，可回看任务" : task.description.trim()}</span>
            </span>
            <span className="dashboard-tile-clock" aria-hidden="true">◷</span>
          </span>
        </button>)}
    </div>
  </section>;
}
