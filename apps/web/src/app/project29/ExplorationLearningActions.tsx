"use client";

import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { VillageTask, VillageTaskCommand } from "./useVillageTasks";
import { VillageTaskForm } from "./VillageTaskForm";
import { needsExplorationClaim } from "./explorationTaskState";

export function ExplorationLearningActions({ task, busy, hasNext, actionsContainer, onComplete, onContinue }: {
  task: VillageTask;
  busy: boolean;
  hasNext: boolean;
  actionsContainer?: HTMLElement | null;
  onComplete: (checkinConfirmed: boolean) => Promise<boolean>;
  onContinue: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const checkin = task.completionMode === "checkin";
  const completed = task.status === "completed";
  const opened = task.openedMaterials ?? [];
  const materialCount = task.materials?.length ?? 0;
  const remaining = task.materials?.filter((_, index) => !opened.includes(index)).length ?? 0;
  const editable = task.status === "available" || task.status === "active" || task.status === "returned";
  const ready = checkin ? confirmed : materialCount > 0 ? remaining === 0 : confirmed;
  const renderAction = (action: ReactNode) => actionsContainer ? createPortal(action, actionsContainer) : action;
  async function finish() {
    if (busy || finishing || !ready || !editable) return;
    setFinishing(true);
    try { await onComplete(checkin && confirmed); }
    finally { setFinishing(false); }
  }
  if (completed) return <div className="ex-learning-actions ex-learning-completed">
    <strong><span aria-hidden="true">✓</span>{checkin ? "签退及入群已确认" : "本板块学习已完成"}</strong>
    <p>完成记录已保存，可以随时返回查看本板块材料。</p>
    {renderAction(<button type="button" className="module-primary" disabled={busy} onClick={onContinue}>{hasNext ? "进入下一板块 →" : "返回任务目录，查看毕业码 →"}</button>)}
  </div>;
  return <div className="ex-learning-actions">
    {checkin ? <>
      <p className="ex-learning-guidance">请按以上说明完成签退，并加入项目培训群，再勾选下方确认。</p>
      <label className="ex-learning-confirm"><input type="checkbox" checked={confirmed} disabled={busy || finishing || !editable} onChange={event => setConfirmed(event.target.checked)} /><span>我已完成签退，并成功进入项目培训群</span></label>
    </> : materialCount ? <>
      <div className="ex-learning-progress"><span>材料打开记录</span><strong>{materialCount - remaining}<small> / {materialCount}</small></strong></div>
      <p className="ex-learning-guidance">{remaining ? `还有 ${remaining} 份材料尚未打开，请先逐份查看。` : "本板块材料均已打开。完成学习后，点击下方按钮进入下一板块。"}</p>
      <p className="ex-learning-disclosure">阅读或观看完成后，即可继续下一板块。</p>
    </> : <>
      <p className="ex-learning-guidance">本板块暂未配置附件，请阅读以上任务说明后确认完成。</p>
      <label className="ex-learning-confirm"><input type="checkbox" checked={confirmed} disabled={busy || finishing || !editable} onChange={event => setConfirmed(event.target.checked)} /><span>我已阅读以上说明，确认完成本板块学习</span></label>
    </>}
    {renderAction(<button type="button" className="module-primary ex-learning-complete-button" disabled={busy || finishing || !editable || !ready} onClick={() => void finish()}>{busy || finishing ? "正在保存完成记录…" : checkin ? "确认完成签退及入群 →" : hasNext ? "完成学习，进入下一板块 →" : "完成学习，返回任务目录 →"}</button>)}
    {checkin && !confirmed && <p className="ex-learning-disclosure">确认完成签退及入群后，即可记录本任务完成。</p>}
  </div>;
}

export function ExplorationAssessmentEntry({ url, onStart }: { url?: string; onStart?: () => void }) {
  let href: string | null = null;
  try { const parsed = new URL(url || ""); if (["http:", "https:"].includes(parsed.protocol)) href = parsed.href; } catch { /* An unconfigured test must not produce an invented destination. */ }
  return <div className="ex-assessment-entry"><div><span>培训测试</span><h3>完成测试，再提交测试结果</h3><p>{href ? "测试将在新页面打开。完成后返回这里，填写结果或结果文档链接，提交审核。" : "测试入口暂未配置，请等待管理员补充实际测试链接。"}</p></div>{href ? <a className="module-primary" href={href} target="_blank" rel="noopener noreferrer" onClick={onStart}>进入测试 ↗</a> : <span className="ex-assessment-unavailable">测试链接待配置</span>}</div>;
}

export function ExplorationAssessmentActions({ task, answer, busy, savedMessage, beforeActions, hasNext, actionsContainer, onAnswer, onAction, onContinue }: {
  task: VillageTask;
  answer: string;
  busy: boolean;
  savedMessage: string;
  beforeActions: ReactNode;
  hasNext: boolean;
  actionsContainer?: HTMLElement | null;
  onAnswer: (answer: string) => void;
  onAction: (command: VillageTaskCommand) => Promise<boolean>;
  onContinue: () => void;
}) {
  const minimumLength = task.minimumAnswerLength ?? (task.assessmentUrl ? 1 : 40);
  const hasTaskFiles = !!task.taskFiles?.length;
  const resultLabel = hasTaskFiles ? "任务成果或结果文档链接" : "测试结果或结果文档链接";
  const renderAction = (action: ReactNode) => actionsContainer ? createPortal(action, actionsContainer) : action;
  if (needsExplorationClaim(task)) return <div className="ex-claim-section"><p>{hasTaskFiles ? "先开始任务并查看任务文件，完成作答后可以提交成果，也可以先保存草稿。" : "完成测试后，可以填写结果并提交审核，也可以先保存草稿。"}</p>{renderAction(<button type="button" className="module-primary" disabled={busy} onClick={() => void onAction("claim")}>{busy ? "正在准备…" : hasTaskFiles ? "开始任务 →" : "填写测试结果 →"}</button>)}</div>;
  return <>
    <VillageTaskForm task={task} answer={answer} busy={busy} savedMessage={savedMessage} beforeActions={beforeActions} minLength={minimumLength} inputLabel={resultLabel} placeholder={hasTaskFiles ? minimumLength <= 1 ? "填写你的任务成果、作答说明或结果文档链接…" : `填写你的任务成果或结果文档链接（至少 ${minimumLength} 字）…` : minimumLength <= 1 ? "填写你的测试结果、简短说明或结果文档链接…" : `填写你的测试结果或结果文档链接（至少 ${minimumLength} 字）…`} actionsContainer={actionsContainer} onAnswer={onAnswer} onAction={onAction} />
    {["pending", "completed"].includes(task.status) && <div className="ex-assessment-continue"><p>{task.status === "pending" ? "测试结果已提交，审核期间可以继续下一板块。毕业码需全部任务完成后解锁。" : "测试审核已通过，可以继续探索下一板块。"}</p>{renderAction(<button type="button" className="module-secondary" disabled={busy} onClick={onContinue}>{hasNext ? "进入下一板块 →" : "返回任务目录，查看毕业码 →"}</button>)}</div>}
  </>;
}
