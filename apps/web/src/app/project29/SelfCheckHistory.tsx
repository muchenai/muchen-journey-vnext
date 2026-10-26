import { useEffect, useRef } from "react";
import type { AISelfCheckRecord } from "../actions";
export function SelfCheckHistory({ task, onClose, records, error }: {
  task: { id: string; title: string };
  records: AISelfCheckRecord[];
  error?: string;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const entries = records.map(record=>({id:record.id,createdAt:record.createdAt,record:record.body,message:record.result || record.status}));
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={dialog} className="self-check-dialog"
    aria-labelledby="self-check-history-title" onCancel={onClose}
    onClick={event => {
      event.stopPropagation();
      if (event.target === event.currentTarget) {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
      }
    }}>
    <header className="self-check-header">
      <div><h2 id="self-check-history-title">历史 AI 自查记录</h2><p>{task.title}</p></div>
      <button type="button" className="dashboard-record-action" onClick={onClose} autoFocus>关闭</button>
    </header>
    <p className="self-check-disclaimer">AI 自查结果仅供参考，最终结果以人工审核为准。</p>
    {error && <p className="self-check-disclaimer" role="alert">{error}</p>}
    <div className="self-check-list">
      {!entries.length ? <div className="self-check-empty"><p>暂无自查记录</p><p>填写学习记录后，点击「开始 AI 自查」，结果会保存在这里。</p></div> :
        entries.map((entry, index) => <details className="dashboard-record self-check-entry" key={entry.id}>
          <summary className="dashboard-record-meta self-check-entry-summary"><strong>第 {entries.length - index} 次自查记录</strong>
            {entry.createdAt ? <time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-CN", { hour12: false })}</time> : <span>旧记录 · 时间未保存</span>}
          </summary>
          <p className="dashboard-record-message">{entry.message}</p>
          <details className="self-check-snapshot"><summary>查看当时的学习记录</summary>
            <p>{entry.record || "旧记录未保存学习内容快照。"}</p>
          </details>
        </details>)}
    </div>
    <footer className="self-check-footer">共 {entries.length} 条记录 · 仅显示当前身份、当前任务的自查记录</footer>
  </dialog>;
}
