"use client";

import { useEffect, useRef } from "react";
import type { TaskReviewFeedback } from "../project-ui/review-feedback";

export function TaskFeedbackDialog({ feedback, title, onClose }: {
  feedback: TaskReviewFeedback; title: string; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => { element.close(); trigger?.focus(); };
  }, []);

  return <dialog ref={dialog} className="self-check-history task-feedback-dialog" aria-labelledby="task-feedback-title"
    onCancel={onClose} onClick={event => {
      event.stopPropagation();
      if (event.target === event.currentTarget) {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
      }
    }}>
    <header className="self-check-history-header">
      <div><h2 id="task-feedback-title">任务反馈</h2><p>{title}</p></div>
      <button type="button" autoFocus onClick={onClose}>关闭</button>
    </header>
    <p className="self-check-history-notice">审核人员的历次反馈 · 最新审核记录在前</p>
    <ol className="self-check-history-list">
      {feedback.records.map(record => <li key={record.id}>
        <div className="self-check-history-meta">
          <strong>提交版本 {record.version} · {record.decision === "PASS" ? "审核通过" : "退回修改"}</strong>
          <time dateTime={record.reviewedAt}>{new Date(record.reviewedAt).toLocaleString("zh-CN", { hour12: false })}</time>
        </div>
        <p>{record.comment || "本次审核未填写总体评论。"}</p>
        {record.dimensions.length > 0 && <details>
          <summary>查看分项审核反馈（{record.dimensions.length} 项）</summary>
          {record.dimensions.map((item, index) => <div key={index} className="task-feedback-dimension">
            <strong>{item.title} · {item.rating === "MEETS" ? "达标" : "待改进"}{item.score === null ? "" : ` · ${item.score} 分`}</strong>
            <p>{item.comment || "未填写分项评论。"}</p>
          </div>)}
        </details>}
      </li>)}
    </ol>
    <footer>共 {feedback.records.length} 条审核记录 · 仅显示当前账号、当前任务的反馈</footer>
  </dialog>;
}
