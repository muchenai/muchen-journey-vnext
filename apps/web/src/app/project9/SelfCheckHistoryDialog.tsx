"use client";

import { useEffect, useRef } from "react";
import type { SelfCheckRecord } from "./self-check-history";

export function SelfCheckHistoryDialog({ title, records, error, onClose }: {
  title: string;
  records: SelfCheckRecord[];
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
    <p className="self-check-history-notice">本地格式自查 · 尚未连接 AI 服务，不包含真实 AI 评分。</p>
    {error ? <p className="self-check-history-error" role="alert">{error}</p>
      : records.length === 0 ? <div className="self-check-history-empty">
        <strong>暂无自查记录</strong>
        <p>填写学习记录后，点击「开始 AI 自查」，结果会保存在这里。</p>
      </div> : <ol className="self-check-history-list">
        {records.map((entry, index) => <li key={entry.id}>
          <div className="self-check-history-meta"><strong>第 {records.length - index} 次自查</strong>
            <time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-CN", { hour12: false })}</time></div>
          <p>{entry.result}</p>
          <details><summary>查看本次学习记录（{entry.body.trim().length} 个有效字符）</summary><p>{entry.body}</p></details>
        </li>)}
      </ol>}
    <footer>{error ? "记录读取失败" : `共 ${records.length} 条记录`} · 仅显示当前身份、当前任务的自查记录
      <span>记录保存在当前浏览器，清除浏览器数据后将无法找回。</span>
    </footer>
  </dialog>;
}
