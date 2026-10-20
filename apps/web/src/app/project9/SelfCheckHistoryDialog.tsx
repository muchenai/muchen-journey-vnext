"use client";

import { useEffect, useRef } from "react";
import type { AISelfCheckRecord } from "../actions";

export function SelfCheckHistoryDialog({ title, records, error, onClose }: {
  title: string;
  records: AISelfCheckRecord[];
  error: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const trigger = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => { element.close(); trigger?.focus(); };
  }, []);

  return <dialog ref={dialog} className="self-check-history" aria-labelledby="self-check-history-title"
    onCancel={onClose} onClick={event => {
      event.stopPropagation();
      if (event.target === event.currentTarget) {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
      }
    }}>
    <header className="self-check-history-header">
      <div><h2 id="self-check-history-title">历史 AI 自查记录</h2><p>{title}</p></div>
      <button type="button" autoFocus onClick={onClose}>关闭</button>
    </header>
    <p className="self-check-history-notice">AI 自查只提供评价和建议，不计分、不代替人工审核。修改文档后可再次自查，最新评价更新至原标题评论，历次评价保留在此处。</p>
    {error && <p className="self-check-history-error" role="alert">{error}</p>}
    {records.length === 0 ? !error && <div className="self-check-history-empty">
        <strong>暂无自查记录</strong>
        <p>填写自己的飞书答题文档链接后，点击「开始 AI 自查」。</p>
      </div> : <ol className="self-check-history-list">
        {records.map((entry, index) => <li key={entry.id}>
          <div className="self-check-history-meta"><strong>第 {records.length - index} 次自查</strong>
            <time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-CN", { hour12: false })}</time></div>
          <p>{entry.status === "COMPLETED" ? "已完成自查；飞书标题评论展示最近一次成功评价" : "自查状态待处理"}{entry.documentRevision ? ` · 文档版本 ${entry.documentRevision}` : ""}</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{entry.result}</p>
          <details><summary>查看本次文档链接</summary><p>{entry.body}</p></details>
        </li>)}
      </ol>}
    <footer>{error ? "本次操作未完成，原因见上方提示" : `共 ${records.length} 条记录`} · 仅显示当前身份、当前任务的自查记录
      <span>记录保存在服务器，刷新页面或更换浏览器后仍可查看。</span>
    </footer>
  </dialog>;
}
