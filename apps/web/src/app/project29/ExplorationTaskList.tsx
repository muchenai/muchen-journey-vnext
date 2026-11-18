"use client";

import type { MouseEvent, ReactNode } from "react";
import type { VillageTask } from "./useVillageTasks";
import type { ExplorationTreasures } from "@/lib/exploration-treasures";
import { ExplorationGraduationTaskCard } from "./ExplorationGraduationTaskCard";
import { canOpenExplorationTask, explorationStatusLabels, needsExplorationClaim } from "./explorationTaskState";
import "./explorationTaskList.css";

type PublishedTask = VillageTask & { order?: number };
type TaskState = VillageTask["status"];
const orderOf = (task: PublishedTask, fallback: number) => Number.isInteger(task.order) && Number(task.order) > 0 ? Number(task.order) : fallback;
const numberLabel = (order: number) => String(order).padStart(2, "0");

function cardState(status: TaskState) {
  return status === "returned" ? "revision" : status === "available" ? "active" : status === "unavailable" || status === "locked" ? "locked" : status;
}
function taskCopy(task: PublishedTask) {
  const status = task.status;
  const assessment = !task.completionMode || task.completionMode === "assessment";
  if (status === "completed") return { note: assessment ? "审核已通过" : task.completionMode === "checkin" ? "已确认培训签退" : "学习已完成", action: "回看任务 →" };
  if (status === "pending") return { note: "已提交，等待审核", action: "回看任务 →" };
  if (status === "returned") return { note: "请按评语修改后重新提交", action: "去修改 →" };
  if (status === "active" && !needsExplorationClaim(task)) return { note: assessment ? "完成测试后提交审核" : task.completionMode === "checkin" ? "签退并成功进入项目培训群" : "打开材料后，进入下一板块", action: "继续任务 →" };
  if (status === "locked") return { note: "上一任务提交后解锁", action: "等待上一任务提交" };
  if (status === "unavailable") return { note: "该任务当前暂不可用", action: "暂不可用" };
  return { note: assessment ? "完成测试后提交审核" : task.completionMode === "checkin" ? "扫码签退，确认进入项目群" : "打开材料即可开始学习", action: assessment ? "查看任务 →" : "开始学习 →" };
}

export function ExplorationTaskList({ tasks, identity, loading = false, error = "", onBack, onOpenTask, onRefresh, treasures, onOpenGraduation,
  panelDecoration, backDecoration,
}: {
  tasks: PublishedTask[];
  identity: string;
  loading?: boolean;
  error?: string;
  onBack: () => void;
  onOpenTask: (id: string) => void;
  onRefresh?: () => void;
  treasures?: ExplorationTreasures;
  onOpenGraduation?: () => void;
  panelDecoration?: ReactNode;
  backDecoration?: ReactNode;
}) {
  const ordered = tasks.map((task, index) => ({ task, order: orderOf(task, index + 1), index }))
    .sort((left, right) => left.order - right.order || left.index - right.index);
  const completed = ordered.filter(({ task }) => task.status === "completed").length;
  const current = ordered.find(({ task }) => task.status === "returned")
    ?? ordered.find(({ task }) => task.status === "active")
    ?? ordered.find(({ task }) => task.status === "available")
    ?? ordered.find(({ task }) => task.status === "pending")
    ?? ordered.find(({ task }) => task.status === "completed");
  const allComplete = ordered.length > 0 && completed === ordered.length;
  const openCurrent = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (current) onOpenTask(current.task.id);
  };
  return <section className="exploration-original-task-list" aria-label="探索营成长任务列表">
    <img className="eotl-background" src="/assets/project29/90975.webp" alt="" />
    <button type="button" className="eotl-back figma-stroke figma-stroke-back"
      onClick={event => { event.stopPropagation(); onBack(); }}>
      {backDecoration}<span className="journey-back-tint" aria-hidden="true" />
      <span className="eotl-back-inset" aria-hidden="true" />
      <span className="eotl-back-content"><span className="eotl-back-arrow"><img src="/assets/project29/59316.svg" alt="" /></span><span className="eotl-back-label">返回主页面</span></span>
    </button>
    <aside className="eotl-next" aria-label="当前学习进度">
      <p className="eotl-greeting">你好，{identity || "新同学"} · 你的成长航线</p>
      <h1><span>{allComplete ? "这一程" : "下一站"}</span><strong>{loading && !ordered.length ? "准备中" : allComplete ? "已完成" : current ? `任务 ${numberLabel(current.order)}` : "等待启程"}</strong></h1>
      <p className="eotl-description">{allComplete ? "你已经完成当前全部探索任务。集齐四件宝藏后，即可在最后一张卡片解锁毕业码。" : "打开材料开始学习，学完后进入下一板块。测试任务按配置完成 AI 评测或人工审核，培训签退后确认进入项目群，完成这一程探索。"}</p>
      <button type="button" className="eotl-continue" disabled={!current || loading} onClick={openCurrent}>
        {allComplete ? "回看学习成果" : current?.task.status === "pending" ? "查看当前提交" : current && needsExplorationClaim(current.task) ? "开始当前任务" : "继续当前任务"}<span aria-hidden="true">→</span>
      </button>
      <div className="eotl-progress" role="progressbar" aria-label="探索营任务完成进度" aria-valuemin={0} aria-valuemax={ordered.length || 1} aria-valuenow={completed}>
        <p><strong>{completed}</strong><span>/{numberLabel(ordered.length)}</span></p><small>完成进度</small>
      </div>
    </aside>
    <section className="eotl-panel figma-stroke figma-stroke-panel holo-panel" aria-labelledby="eotl-title">
      {panelDecoration}<div className="journey-task-panel-tint eotl-panel-tint" aria-hidden="true" />
      <header className="eotl-panel-heading"><div><span>探索营</span><h2 id="eotl-title">全部成长任务</h2></div>
        {onRefresh && <button type="button" className="eotl-refresh" disabled={loading} onClick={event => { event.stopPropagation(); onRefresh(); }}>刷新任务 ↻</button>}
      </header>
      <div className="eotl-task-scroll" role="region" aria-label="全部成长任务，可向下滚动" tabIndex={0}>
        {error && <p className="eotl-error" role="alert">{error}</p>}
        {loading && !ordered.length ? <p className="eotl-empty" role="status">正在读取探索任务…</p> : !ordered.length ? <p className="eotl-empty">暂时没有已发布的探索任务，任务发布后会在这里显示。</p> : null}
        <div className="journey-task-grid">
          {ordered.map(({ task, order }) => {
            const copy = taskCopy(task);
            const unavailable = !canOpenExplorationTask(task);
            return <button type="button" key={task.id} className={`journey-task-card journey-task-${cardState(task.status)}`}
              data-task-id={task.id} data-task-order={order} data-status={task.status} disabled={unavailable}
              aria-label={`${task.title}，${explorationStatusLabels[task.status] ?? "待解锁"}`}
              onClick={event => { event.stopPropagation(); if (!unavailable) onOpenTask(task.id); }}>
              <span className="journey-task-icon"><img src="/assets/project29/d6a61.webp" alt="" /></span>
              <span className="journey-task-status">{explorationStatusLabels[task.status] ?? "待解锁"}</span>
              <span className="journey-task-number">{numberLabel(order)}</span>
              <span className="journey-task-title">{task.title}</span>
              <span className="journey-task-description">{task.description}</span>
              <span className="journey-task-footer"><span>{copy.note}</span><strong>{copy.action}</strong></span>
            </button>;
          })}
          <ExplorationGraduationTaskCard order={ordered.length + 1} treasures={treasures} loading={loading} onOpen={() => onOpenGraduation?.()} />
        </div>
      </div>
      <div className="eotl-panel-inset" aria-hidden="true" />
    </section>
  </section>;
}
