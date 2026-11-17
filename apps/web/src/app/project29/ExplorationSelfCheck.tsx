"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ExplorationSelfCheckRecord } from "@/lib/exploration-self-check";
import type { VillageTask } from "./useVillageTasks";

type HistoryState = { taskId: string; items: ExplorationSelfCheckRecord[]; loading: boolean; error: string };
type SelfCheckResult = { record: ExplorationSelfCheckRecord; items: ExplorationSelfCheckRecord[] };
const emptyHistory = (taskId: string): HistoryState => ({ taskId, items: [], loading: true, error: "" });

export function useExplorationSelfChecks(taskId: string) {
  const [state, setState] = useState<HistoryState>(() => emptyHistory(taskId));
  const generation = useRef(0);
  const load = useCallback(async () => {
    const request = ++generation.current;
    setState(previous => ({ ...(previous.taskId === taskId ? previous : emptyHistory(taskId)), loading: true, error: "" }));
    try {
      const response = await fetch(`/api/learner/exploration?task=${encodeURIComponent(taskId)}&selfChecks=1`, { cache: "no-store" });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "历史自测记录读取失败，请重试。");
      if (!Array.isArray(result.items)) throw new Error("历史自测记录格式不正确，请重试。");
      if (request === generation.current) setState({ taskId, items: result.items, loading: false, error: "" });
    } catch (error) {
      if (request === generation.current) setState(previous => ({ ...(previous.taskId === taskId ? previous : emptyHistory(taskId)), loading: false, error: error instanceof Error ? error.message : "历史自测记录读取失败，请重试。" }));
    }
  }, [taskId]);
  useEffect(() => {
    void load();
    return () => { ++generation.current; };
  }, [load]);
  const accept = (items: ExplorationSelfCheckRecord[]) => {
    ++generation.current;
    setState({ taskId, items, loading: false, error: "" });
  };
  return { ...(state.taskId === taskId ? state : emptyHistory(taskId)), load, accept };
}

const formatDate = (date: string) => Number.isFinite(Date.parse(date)) ? new Date(date).toLocaleString("zh-CN", { hour12: false }) : "时间未记录";

export function ExplorationSelfCheck({ task, answer, busy, onRun }: {
  task: VillageTask;
  answer: string;
  busy: boolean;
  onRun: () => Promise<SelfCheckResult | null>;
}) {
  const history = useExplorationSelfChecks(task.id);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const runningRef = useRef(false);
  const runGeneration = useRef(0);
  useEffect(() => () => { ++runGeneration.current; }, [task.id]);
  const editable = task.status === "active" || task.status === "returned";
  const minimumLength = Math.max(1, task.minimumAnswerLength ?? 40);
  const enoughContent = Array.from(answer.replace(/\s/gu, "")).length >= minimumLength;
  const withinLimit = answer.length <= 8000;
  const latest = history.items[0];
  const changed = !!latest && latest.body !== answer;
  async function run() {
    if (!editable || !enoughContent || !withinLimit || busy || runningRef.current) return;
    const request = ++runGeneration.current;
    runningRef.current = true;
    setRunning(true); setRunError("");
    try {
      const result = await onRun();
      if (request !== runGeneration.current) return;
      if (result) history.accept(result.items);
      else setRunError("本次自测未完成，请查看下方提示后重试；也可以先读取历史记录核对。");
    } catch {
      if (request === runGeneration.current) setRunError("暂未确认自测结果，请读取历史记录核对后重试。");
    } finally {
      if (request === runGeneration.current) { runningRef.current = false; setRunning(false); }
    }
  }
  return <section className="ex-self-check" aria-label="学习成果 AI 自测">
    <div className="ex-self-check-heading"><strong>提交前，先检查你的学习成果</strong><span>AI 自测 · 成果反馈</span></div>
    <p className="ex-self-check-intro">自测反馈供修改时参考，最终结果以人工审核为准。</p>
    <div className="ex-self-check-actions">
      <button type="button" className="module-secondary ex-self-check-run" disabled={!editable || !enoughContent || !withinLimit || busy || running} aria-busy={running} onClick={() => void run()}>{running ? "正在进行 AI 自测…" : "✦ 开始 AI 自测"}</button>
      <button type="button" className="ex-self-check-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)}>历史自测记录{history.items.length > 0 ? ` · ${history.items.length}` : ""} <span aria-hidden="true">{historyOpen ? "⌃" : "⌄"}</span></button>
    </div>
    {!editable ? <p className="ex-self-check-hint">{task.status === "completed" ? "任务已完成，可以回看历史自测记录。" : task.status === "pending" ? "任务正在审核中，可以回看历史自测记录。" : "接取任务后可以使用自测。"}</p> : !enoughContent && <p className="ex-self-check-hint">{minimumLength === 1 ? "填写测试结果后，可开始自测。" : `填写至少 ${minimumLength} 个非空白字符后，可开始自测。`}</p>}
    {editable && !withinLimit && <p className="ex-self-check-error" role="alert">学习成果不能超过 8000 字，请精简后再自测。</p>}
    {runError && <p className="ex-self-check-error" role="alert">{runError}</p>}
    {latest && <div className="ex-self-check-latest" aria-live="polite">
      <div className="ex-self-check-result-heading"><strong>最近一次自测反馈</strong><time dateTime={latest.createdAt}>{formatDate(latest.createdAt)}</time></div>
      {latest.status === "FAILED" && <p className="ex-self-check-error" role="alert">本次 AI 自测未完成，可查看提示后重试。</p>}
      {latest.taskVersionId !== task.versionId && <p className="ex-self-check-changed" role="status">这条反馈来自历史任务版本。请按当前任务要求重新自测。</p>}
      {changed && <p className="ex-self-check-changed" role="status">学习成果已修改，以下反馈对应上一次自测时的内容。可以再次自测，保留新的记录。</p>}
      <p className="ex-self-check-result">{latest.result}</p>
    </div>}
    {historyOpen && <div className="ex-self-check-history" role="region" aria-label="历史自测记录">
      <div className="ex-self-check-history-heading"><strong>历史自测记录</strong><button type="button" disabled={history.loading || running || busy} onClick={() => void history.load()}>重新读取 ↻</button></div>
      {history.loading ? <p className="ex-self-check-hint" role="status">正在读取历史自测记录…</p> : history.error ? <div className="ex-self-check-history-error"><p className="ex-self-check-error" role="alert">{history.error}</p><button type="button" disabled={busy} onClick={() => void history.load()}>重试读取</button></div> : !history.items.length ? <p className="ex-self-check-hint">暂无自测记录。填写学习成果后，点击“开始 AI 自测”，每次反馈都会保存在这里。</p> : <div className="ex-self-check-records">{history.items.map((record, index) => <details className="ex-self-check-record" key={record.id}>
        <summary><strong>第 {history.items.length - index} 次自测</strong><time dateTime={record.createdAt}>{formatDate(record.createdAt)}</time></summary>
        <p className="ex-self-check-record-mode">{record.status === "FAILED" ? "AI 自测 · 暂未完成" : "AI 自测 · 成果反馈"}{record.taskVersionId !== task.versionId ? " · 历史任务版本" : ""}</p>
        <p className="ex-self-check-result">{record.result}</p>
        <details className="ex-self-check-snapshot"><summary>查看当时的学习成果</summary><p>{record.body}</p></details>
      </details>)}</div>}
    </div>}
  </section>;
}
