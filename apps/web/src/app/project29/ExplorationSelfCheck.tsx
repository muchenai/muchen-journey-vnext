"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ExplorationSelfCheckRecord } from "@/lib/exploration-self-check";
import type { VillageTask } from "./useVillageTasks";

type HistoryState = { taskId: string; scope: string; items: ExplorationSelfCheckRecord[]; loading: boolean; error: string };
type SelfCheckResult = { record: ExplorationSelfCheckRecord; items: ExplorationSelfCheckRecord[] };
type HistoryOptions = { versionId?: string; pending?: boolean; records?: ExplorationSelfCheckRecord[] };
const emptyHistory = (taskId: string, scope: string, items?: ExplorationSelfCheckRecord[]): HistoryState =>
  ({ taskId, scope, items: items ?? [], loading: items === undefined, error: "" });

export function useExplorationSelfChecks(taskId: string, enabled = true, options: HistoryOptions = {}) {
  const { versionId, pending = false, records } = options;
  const scope = JSON.stringify([taskId, versionId]);
  const [state, setState] = useState<HistoryState>(() => emptyHistory(taskId, scope, records));
  const generation = useRef(0);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const active = useRef(enabled);
  active.current = enabled;
  const projection = useRef<{ scope: string; items: ExplorationSelfCheckRecord[] } | null>(null);
  const inFlight = useRef<{ scope: string; request: number; promise: Promise<ExplorationSelfCheckRecord[] | undefined> } | null>(null);
  const accept = useCallback((items: ExplorationSelfCheckRecord[]) => {
    ++generation.current;
    inFlight.current = null;
    setState({ taskId, scope, items, loading: false, error: "" });
  }, [taskId, scope]);
  const load = useCallback((quiet = false): Promise<ExplorationSelfCheckRecord[] | undefined> => {
    if (!enabled || !active.current || currentScope.current !== scope) return Promise.resolve(undefined);
    if (inFlight.current?.scope === scope) return inFlight.current.promise;
    const request = ++generation.current;
    setState(previous => {
      const current = previous.scope === scope ? previous : emptyHistory(taskId, scope);
      return { ...current, loading: !quiet && current.items.length === 0, error: "" };
    });
    const operation = (async () => {
      try {
        const response = await fetch(`/api/learner/exploration?task=${encodeURIComponent(taskId)}&selfChecks=1`, { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "历史自测记录读取失败，请重试。");
        if (!Array.isArray(result.items)) throw new Error("历史自测记录格式不正确，请重试。");
        if (request === generation.current && active.current && currentScope.current === scope) {
          setState({ taskId, scope, items: result.items, loading: false, error: "" });
          return result.items as ExplorationSelfCheckRecord[];
        }
      } catch (error) {
        if (request === generation.current && active.current && currentScope.current === scope) setState(previous => ({
          ...(previous.scope === scope ? previous : emptyHistory(taskId, scope)), loading: false,
          error: error instanceof Error ? error.message : "历史自测记录读取失败，请重试。",
        }));
      }
    })().finally(() => {
      if (inFlight.current?.request === request) inFlight.current = null;
    });
    inFlight.current = { scope, request, promise: operation };
    return operation;
  }, [taskId, enabled, scope]);
  useEffect(() => {
    active.current = enabled;
    void load();
    return () => { active.current = false; ++generation.current; inFlight.current = null; };
  }, [load, enabled]);
  useEffect(() => {
    if (!enabled || records === undefined) return;
    projection.current = { scope, items: records };
    accept(records); // A completed POST result supersedes an older history GET.
  }, [enabled, records, scope, accept]);
  const projected = records !== undefined && (projection.current?.scope !== scope || projection.current.items !== records);
  const visible = projected ? emptyHistory(taskId, scope, records)
    : state.scope === scope ? state : emptyHistory(taskId, scope, records);
  const completionCandidate = visible.items.find(item => (!versionId || item.taskVersionId === versionId)
    && item.status === "COMPLETED" && item.passed === true && item.taskCompleted !== true);
  const completionIdentity = completionCandidate ? `${scope}:${completionCandidate.id}` : "";
  const completionReads = useRef({ identity: "", count: 0 });
  if (completionReads.current.identity !== completionIdentity) completionReads.current = { identity: completionIdentity, count: 0 };
  // A history read can land after grading commits but before automatic completion.
  // Briefly confirm that boundary without turning a blocked completion into an
  // endless "running" state.
  const confirmingCompletion = !!completionCandidate && completionReads.current.count < 3;
  const waiting = pending || visible.items.some(item => (!versionId || item.taskVersionId === versionId)
    && (item.status === "RUNNING" || item.status === "COMPLETED" && item.commentStatus === "PENDING")) || confirmingCompletion;
  useEffect(() => {
    if (!enabled || !waiting || typeof window === "undefined") return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      if (completionIdentity && completionReads.current.identity === completionIdentity) completionReads.current.count++;
      await load(true);
      if (!stopped) timer = window.setTimeout(() => { void poll(); }, 2000);
    };
    timer = window.setTimeout(() => { void poll(); }, 2000);
    return () => { stopped = true; if (timer !== undefined) window.clearTimeout(timer); };
  }, [enabled, waiting, load, completionIdentity]);
  return { ...visible, confirmingCompletion, completionUnconfirmed: !!completionCandidate, load, accept };
}

const formatDate = (date: string) => Number.isFinite(Date.parse(date)) ? new Date(date).toLocaleString("zh-CN", { hour12: false }) : "时间未记录";

function documentUrl(value: string): string | null {
  for (const match of value.match(/https:\/\/[^\s<>"'`]+/giu) ?? []) {
    try {
      const url = new URL(match.replace(/[，。；！？,;!?)）\]】]+$/u, ""));
      if (!url.username && !url.password && ["feishu.cn", "larksuite.com"].some(host => url.hostname === host || url.hostname.endsWith(`.${host}`)) && /^\/(docx|docs|wiki)\/[^/]+\/?$/u.test(url.pathname)) return url.href;
    } catch { /* An invalid link remains input for server-side validation. */ }
  }
  return null;
}
function documentIdentity(value: string): string | null {
  const valid = documentUrl(value);
  if (!valid) return null;
  const url = new URL(valid);
  return `${url.origin}${url.pathname.replace(/\/$/u, "")}`;
}
function awaitingConfirmation(record: ExplorationSelfCheckRecord) {
  return record.status === "RUNNING" || record.commentStatus === "PENDING" || record.commentStatus === "UNCERTAIN";
}
function ScoreFeedback({ record, task }: { record: ExplorationSelfCheckRecord; task: VillageTask }) {
  const maxScore = record.maxScore ?? 100;
  const passScore = task.passScore;
  if (record.status !== "COMPLETED" || typeof record.score !== "number" || !Number.isFinite(record.score)
      || !Number.isFinite(maxScore) || maxScore <= 0 || record.score < 0 || record.score > maxScore) return null;
  const thresholdValid = Number.isFinite(passScore) && passScore >= 0 && passScore <= maxScore;
  const passed = thresholdValid && record.passed === true && record.score >= passScore;
  const failed = thresholdValid && record.passed === false && record.score < passScore;
  const completed = passed && record.taskCompleted === true && task.status === "completed" && record.taskVersionId === task.versionId;
  return <div className="ex-self-check-score" aria-label="AI 评测得分">
    <p><strong>总分 {record.score} / {maxScore}</strong>{thresholdValid && <span> · 通过线 {passScore} 分</span>}</p>
    {!!record.dimensions?.length && <ul aria-label="评测维度得分">{record.dimensions.filter(dimension =>
      Number.isFinite(dimension.score) && Number.isFinite(dimension.maxScore)
      && dimension.maxScore > 0 && dimension.score >= 0 && dimension.score <= dimension.maxScore
    ).map((dimension, index) => <li key={`${dimension.id}:${index}`}>
      <strong>{dimension.name}：{dimension.score} / {dimension.maxScore}</strong>
      {dimension.feedback && <p>{dimension.feedback}</p>}
    </li>)}</ul>}
    <p className={failed ? "ex-self-check-error" : "ex-self-check-hint"} role="status">{completed
      ? "评测达标，任务已自动完成。"
      : passed ? "评测已达标，任务完成状态尚未确认，请刷新任务状态。"
      : failed ? "评测未达标，请根据维度反馈修改成果后重新评测。"
      : "评测结果暂未确认，请重新读取任务状态。"}</p>
  </div>;
}
function AnalysisFeedback({ record, task }: { record: ExplorationSelfCheckRecord; task: VillageTask }) {
  if (record.status === "FAILED") {
    // Older failures stored the same reason in all three fields. A failed
    // attempt has no analysis to render, so show that reason once.
    const reason = record.errorMessage?.trim() || record.result.trim() || record.commentMessage?.trim();
    return <p className="ex-self-check-error" role="alert">本次 AI 自测未完成{reason ? `：${reason}` : "，请稍后重试。"}</p>;
  }
  if (record.status === "RUNNING") return <p className="ex-self-check-hint" role="status">本次 AI 自测正在处理，请稍后重新读取记录。</p>;
  const commentExplainsError = ["FAILED", "UNCERTAIN", "PENDING"].includes(record.commentStatus ?? "");
  return <>
    <ScoreFeedback record={record} task={task} />
    {record.result && <p className="ex-self-check-result">{record.result}</p>}
    {record.errorMessage && !commentExplainsError && record.errorMessage.trim() !== record.result.trim() && <p className="ex-self-check-error" role="alert">{record.errorMessage}</p>}
  </>;
}
function CommentFeedback({ record }: { record: ExplorationSelfCheckRecord }) {
  const isDocument = record.inputKind === "document" || record.mode === "DOCUMENT_AI";
  const href = record.documentUrl ? documentUrl(record.documentUrl) : null;
  if (record.status !== "COMPLETED") return isDocument && href
    ? <div className="ex-self-check-comment-status"><a href={href} target="_blank" rel="noopener noreferrer">打开答题文档 ↗</a></div> : null;
  let message = "";
  if (record.commentStatus === "SENT") message = "反馈已写入文档标题评论，并 @ 文档所有者。";
  else if (record.commentStatus === "FAILED") message = "分析已完成，文档评论发送失败。分析结果已保留在本页；请按提示处理评论问题。";
  else if (record.commentStatus === "UNCERTAIN") message = "文档评论是否送达暂未确认。请先到文档核对并重新读取记录，暂勿重复自测，以免重复评论。";
  else if (record.commentStatus === "PENDING") message = "分析已完成，正在确认文档评论。请重新读取记录，暂勿重复自测。";
  else if (isDocument) message = "这条历史记录未保存评论送达状态，请到文档核对。";
  if (!message) return null;
  const detail = record.errorMessage?.trim() || record.commentMessage?.trim();
  return <div className="ex-self-check-comment-status" data-comment-status={record.commentStatus ?? "UNKNOWN"}>
    <p className={record.commentStatus === "FAILED" || record.commentStatus === "UNCERTAIN" ? "ex-self-check-error" : "ex-self-check-hint"} role="status">{message}</p>
    {detail && detail !== message && detail !== record.result.trim() && <p className="ex-self-check-hint">{detail}</p>}
    {isDocument && href && <a href={href} target="_blank" rel="noopener noreferrer">打开结果文档，查看标题评论 ↗</a>}
  </div>;
}

export function ExplorationSelfCheck({ task, answer, busy, pending = false, records, onRun }: {
  task: VillageTask;
  answer: string;
  busy: boolean;
  pending?: boolean;
  records?: ExplorationSelfCheckRecord[];
  onRun: () => Promise<SelfCheckResult | null>;
}) {
  const aiAssessment = task.reviewMode === "AI" && (task.completionMode ?? "assessment") === "assessment";
  const history = useExplorationSelfChecks(task.id, aiAssessment, { versionId: task.versionId, pending, records });
  const [historyOpen, setHistoryOpen] = useState(false);
  const taskScope = JSON.stringify([task.id, task.versionId]);
  const [activity, setActivity] = useState({ scope: taskScope, running: false, error: "" });
  const running = activity.scope === taskScope && activity.running;
  const runError = activity.scope === taskScope ? activity.error : "";
  const setRunning = (value: boolean) => setActivity(previous => ({
    scope: taskScope, running: value, error: previous.scope === taskScope ? previous.error : "",
  }));
  const setRunError = (value: string) => setActivity(previous => ({
    scope: taskScope, running: previous.scope === taskScope && previous.running, error: value,
  }));
  const runningRef = useRef(false);
  const runGeneration = useRef(0);
  useEffect(() => {
    runningRef.current = false;
    return () => { ++runGeneration.current; };
  }, [task.id, task.versionId]);
  const editable = task.status === "active" || task.status === "returned";
  // Self-check accepts a brief answer or a document URL. Submission rules are separate.
  const enoughContent = answer.trim().length > 0;
  const withinLimit = answer.length <= 8000;
  const latest = history.items[0];
  const changed = !!latest && latest.body !== answer;
  const currentDocument = documentIdentity(answer);
  const unconfirmed = history.items.find(record => record.taskVersionId === task.versionId && awaitingConfirmation(record)
    && (record.body === answer || !!currentDocument && documentIdentity(record.documentUrl || record.body) === currentDocument));
  const scoreRunning = pending || running || history.items.some(record => record.taskVersionId === task.versionId && record.status === "RUNNING");
  const commentPending = !scoreRunning && history.items.some(record => record.taskVersionId === task.versionId
    && record.status === "COMPLETED" && record.commentStatus === "PENDING");
  async function refreshStatus() {
    const items = await history.load();
    if (items) setRunError("");
  }
  async function run() {
    if (!aiAssessment || !editable || !enoughContent || !withinLimit || busy || runningRef.current
        || scoreRunning || history.confirmingCompletion || unconfirmed) return;
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
  if (!aiAssessment) return null;
  return <section className="ex-self-check" aria-label="学习成果 AI 自测">
    <div className="ex-self-check-heading"><strong>按任务评分标准评测你的成果</strong><span>AI 评测 · 维度评分</span></div>
    <p className="ex-self-check-intro">可直接填写文字，或粘贴飞书文档链接。文字反馈显示在本页；文档读取后会将反馈写入标题评论，并 @ 文档所有者。链接旁的文字会作为补充说明。AI 按本任务的评分维度和参考答案评测，达到 {task.passScore} 分后自动完成任务；未达标可修改后重新评测。</p>
    <div className="ex-self-check-actions">
      <button type="button" className="module-secondary ex-self-check-run" disabled={!editable || !enoughContent || !withinLimit || busy || scoreRunning || history.confirmingCompletion || !!unconfirmed} aria-busy={scoreRunning || commentPending || history.confirmingCompletion} onClick={() => void run()}>{scoreRunning ? "正在进行 AI 自测…" : history.confirmingCompletion ? "正在确认任务完成状态…" : commentPending ? "正在确认文档评论…" : "✦ 开始 AI 自测"}</button>
      <button type="button" className="ex-self-check-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)}>历史自测记录{history.items.length > 0 ? ` · ${history.items.length}` : ""} <span aria-hidden="true">{historyOpen ? "⌃" : "⌄"}</span></button>
      {(unconfirmed || history.completionUnconfirmed || runError) && <button type="button" className="ex-self-check-history-toggle" disabled={history.loading || running || busy} onClick={() => void refreshStatus()}>重新读取自测状态 ↻</button>}
    </div>
    {!editable ? <p className="ex-self-check-hint">{task.status === "completed" ? "任务已完成，可以回看历史自测记录。" : task.status === "pending" ? "任务正在审核中，可以回看历史自测记录。" : "接取任务后可以使用自测。"}</p> : !enoughContent && <p className="ex-self-check-hint">填写文字成果或飞书文档链接后，可开始自测。</p>}
    {scoreRunning ? <p className="ex-self-check-hint" role="status">正在进行 AI 自测，可以关闭任务卡，稍后再次打开查看进度和结果。</p>
      : unconfirmed && <p className="ex-self-check-hint" role="status">这份成果的文档评论尚未确认完成，暂勿重复发送；可以重新读取状态核对。</p>}
    {editable && !withinLimit && <p className="ex-self-check-error" role="alert">学习成果不能超过 8000 字，请精简后再自测。</p>}
    {runError && <p className="ex-self-check-error" role="alert">{runError}</p>}
    {history.error && (unconfirmed || runError) && !historyOpen && <p className="ex-self-check-error" role="alert">{history.error}</p>}
    {latest && <div className="ex-self-check-latest" aria-live="polite">
      <div className="ex-self-check-result-heading"><strong>最近一次自测反馈</strong><time dateTime={latest.createdAt}>{formatDate(latest.createdAt)}</time></div>
      {latest.taskVersionId !== task.versionId && <p className="ex-self-check-changed" role="status">这条反馈来自历史任务版本。请按当前任务要求重新自测。</p>}
      {changed && <p className="ex-self-check-changed" role="status">学习成果已修改，以下反馈对应上一次自测时的内容。可以再次自测，保留新的记录。</p>}
      <AnalysisFeedback record={latest} task={task} />
      <CommentFeedback record={latest} />
    </div>}
    {historyOpen && <div className="ex-self-check-history" role="region" aria-label="历史自测记录">
      <div className="ex-self-check-history-heading"><strong>历史自测记录</strong><button type="button" disabled={history.loading || running || busy} onClick={() => void refreshStatus()}>重新读取 ↻</button></div>
      {history.loading ? <p className="ex-self-check-hint" role="status">正在读取历史自测记录…</p> : history.error ? <div className="ex-self-check-history-error"><p className="ex-self-check-error" role="alert">{history.error}</p><button type="button" disabled={busy} onClick={() => void refreshStatus()}>重试读取</button></div> : !history.items.length ? <p className="ex-self-check-hint">暂无自测记录。填写学习成果后，点击“开始 AI 自测”，每次反馈都会保存在这里。</p> : <div className="ex-self-check-records">{history.items.map((record, index) => <details className="ex-self-check-record" key={record.id}>
        <summary><strong>第 {history.items.length - index} 次自测</strong><time dateTime={record.createdAt}>{formatDate(record.createdAt)}</time></summary>
        <p className="ex-self-check-record-mode">{record.status === "FAILED" ? "AI 自测 · 暂未完成" : record.status === "RUNNING" ? "AI 自测 · 正在处理" : "AI 自测 · 成果反馈"}{record.inputKind === "document" || record.mode === "DOCUMENT_AI" ? " · 飞书文档" : " · 文字成果"}{record.taskVersionId !== task.versionId ? " · 历史任务版本" : ""}</p>
        <AnalysisFeedback record={record} task={task} />
        <CommentFeedback record={record} />
        <details className="ex-self-check-snapshot"><summary>查看当时的学习成果</summary><p>{record.body}</p></details>
      </details>)}</div>}
    </div>}
  </section>;
}
