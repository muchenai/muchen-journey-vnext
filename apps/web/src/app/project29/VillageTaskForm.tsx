import { useState } from "react";
import type { VillageTask, VillageTaskCommand } from "./useVillageTasks";

export function VillageTaskForm({ task, answer, busy, savedMessage = "", onAnswer, onAction }: {
  task: VillageTask;
  answer: string;
  busy: boolean;
  savedMessage?: string;
  onAnswer: (answer: string) => void;
  onAction: (command: VillageTaskCommand) => Promise<boolean>;
}) {
  const [confirmCancel, setConfirmCancel] = useState(false);
  const editable = task.status === "active" || task.status === "returned";
  const cancelling = confirmCancel && task.status === "active";
  return <form onSubmit={event => {
    event.preventDefault();
    if (editable && !busy && !cancelling) void onAction("submit");
  }}>
    <label className="module-field">成果说明或作品链接
      <textarea required minLength={40} maxLength={8000} rows={5}
        disabled={busy || !editable || cancelling}
        value={answer} onChange={event => onAnswer(event.target.value)}
        placeholder="写下你的分析过程、结果与作品链接（至少 40 字）…" />
    </label>
    <div className="village-draft-feedback" role="status" aria-live="polite" aria-atomic="true">
      {savedMessage && !busy && <span><span aria-hidden="true">✓</span> {savedMessage}</span>}
    </div>
    {cancelling && <section className="village-cancel-confirm" aria-labelledby="village-cancel-title">
      <strong id="village-cancel-title">确认取消接取这个任务？</strong>
      <p>取消后任务恢复为“可接取”，你可以以后重新接取。已保存的草稿会保留。</p>
      {answer !== task.answer && <p className="village-cancel-unsaved">当前还有未保存的内容，取消接取不会自动保存这些修改。若要保留，请先返回保存草稿。</p>}
      <div className="village-task-actions">
        <button type="button" className="module-secondary" disabled={busy} onClick={() => setConfirmCancel(false)}>暂不取消</button>
        <button type="button" className="module-secondary" disabled={busy} onClick={() => { if (task.status === "active" && !busy) void onAction("cancel"); }}>{busy ? "正在取消…" : "确认取消接取"}</button>
      </div>
    </section>}
    <div className="village-task-actions">
      {task.status === "active" && <button type="button" className="module-secondary" disabled={busy || cancelling} onClick={() => setConfirmCancel(true)}>取消接取</button>}
      {editable && <button type="button" className="module-secondary" disabled={busy || cancelling} onClick={() => { if (!busy && !cancelling) void onAction("draft"); }}>保存草稿</button>}
      <button type="submit" className="module-primary" disabled={busy || !editable || cancelling}>
        {busy ? "正在保存…" : task.status === "pending" ? "已提交，等待审核" : task.status === "completed" ? "已完成" : task.status === "returned" ? "重新提交审核" : task.status === "unavailable" ? "暂不可用" : "提交审核"}
      </button>
    </div>
  </form>;
}
