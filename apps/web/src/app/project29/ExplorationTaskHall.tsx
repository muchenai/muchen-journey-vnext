"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { ExplorationSelfCheck } from "./ExplorationSelfCheck";
import { ExplorationLearningMaterial } from "./ExplorationLearningMaterial";
import { ExplorationLearningActions, ExplorationAssessmentActions, ExplorationAssessmentEntry } from "./ExplorationLearningActions";
import type { ExplorationSelfCheckRecord } from "@/lib/exploration-self-check";
import type { ExplorationTreasures } from "@/lib/exploration-treasures";
import { isVillageTaskClaimed, type VillageTask, type VillageTaskCommand } from "./useVillageTasks";
import { canOpenExplorationTask, explorationStatusLabels, needsExplorationClaim } from "./explorationTaskState";
import { useCanvasDialogBounds } from "./useCanvasDialogBounds";
import "./explorationTaskHall.css";

export type ExplorationLayout = "cards" | "list" | "path";
type StatusFilter = "all" | "locked" | "active" | "pending" | "returned" | "completed";
const layouts: { id: ExplorationLayout; letter: string; title: string; description: string }[] = [
  { id: "cards", letter: "A", title: "卡片大厅", description: "浏览任务，随时开始" },
  { id: "list", letter: "B", title: "学习清单", description: "一目了然，专注推进" },
  { id: "path", letter: "C", title: "成长航线", description: "看见全貌，自由探索" },
];

function failureMessage(value: unknown, fallback: string) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "message" in value && typeof value.message === "string") return value.message;
  return fallback;
}
const noTreasures = (): ExplorationTreasures => ({ total: 4, count: 0, items: [], pendingDrops: [] });
const isAiAssessment = (task: VillageTask) => task.reviewMode === "AI" && (task.completionMode ?? "assessment") === "assessment";
type SelfCheckState = {
  taskId: string;
  versionId: string;
  pending: boolean;
  items?: ExplorationSelfCheckRecord[];
};
function assessmentHref(value?: string) {
  try { const url = new URL(value || ""); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}

export function useExplorationTasks(enabled = true) {
  const [tasks, setTasks] = useState<VillageTask[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selfCheckState, setSelfCheckState] = useState<SelfCheckState | null>(null);
  const [treasures, setTreasures] = useState<ExplorationTreasures>(noTreasures);
  const writing = useRef(false);
  const generation = useRef(0);
  const currentTasks = useRef(tasks);
  const writingFinished = useRef<Promise<void>>(Promise.resolve());
  const releaseWriting = useRef<(() => void) | null>(null);
  const learningQueue = useRef<Promise<unknown>>(Promise.resolve());
  const materialRequests = useRef(new Map<string, Promise<VillageTask | null>>());
  const refreshInFlight = useRef<Promise<VillageTask[] | undefined> | null>(null);
  const selfCheckRequests = useRef(new Map<string, { key: string; revision: VillageTask["revision"] }>());
  const refresh = useCallback(() => {
    if (!enabled || writing.current) return Promise.resolve(undefined);
    if (refreshInFlight.current) return refreshInFlight.current;
    const revision = ++generation.current;
    const operation = (async () => {
      try {
        const response = await fetch("/api/learner/exploration", { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(failureMessage(result.error, "探索任务暂时无法读取，请重试。"));
        if (revision !== generation.current) return;
        currentTasks.current = Array.isArray(result.items) ? result.items : [];
        setTasks(currentTasks.current);
        setTreasures(result.treasures ?? noTreasures());
        setError("");
        return currentTasks.current;
      } catch (error) {
        if (revision === generation.current) setError(error instanceof Error ? error.message : "探索任务暂时无法读取。");
      } finally { if (revision === generation.current) setLoading(false); }
    })().finally(() => { if (refreshInFlight.current === operation) refreshInFlight.current = null; });
    refreshInFlight.current = operation;
    return operation;
  }, [enabled]);
  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const check = () => { if (!document.hidden) void refresh(); };
    const timer = window.setInterval(check, 5000);
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    return () => { ++generation.current; refreshInFlight.current = null; clearInterval(timer); window.removeEventListener("focus", check); document.removeEventListener("visibilitychange", check); };
  }, [refresh]);

  function beginWriting() {
    writing.current = true;
    refreshInFlight.current = null;
    writingFinished.current = new Promise(resolve => { releaseWriting.current = resolve; });
    ++generation.current; setBusy(true); setError("");
  }
  function finishWriting() {
    writing.current = false; setBusy(false);
    const release = releaseWriting.current; releaseWriting.current = null; release?.();
  }
  function replaceTask(updated: VillageTask) {
    currentTasks.current = currentTasks.current.map(row => row.id === updated.id ? updated : row);
    setTasks(currentTasks.current);
  }

  async function mutate(task: VillageTask, command: VillageTaskCommand, answer: string) {
    if (command === "cancel") {
      setError("探索营任务接取后不能取消。");
      return null;
    }
    if (writing.current || !canOpenExplorationTask(task)) return null;
    if (command === "submit" && isAiAssessment(task)) {
      setError("本任务使用 AI 评测，请达到通过线后自动完成任务。");
      return null;
    }
    beginWriting();
    try {
      const key = crypto.randomUUID();
      const response = await fetch("/api/learner/exploration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command, taskId: task.id, versionId: task.versionId, revision: task.revision, key, answer }) });
      const result = await response.json();
      if (!response.ok) throw new Error(failureMessage(result.error, "操作未完成，请重试。"));
      const updated = (result.data ?? result) as VillageTask;
      if (!updated.id) throw new Error("任务状态未能更新，请刷新后重试。");
      replaceTask(updated);
      return updated;
    } catch (error) { setError(error instanceof Error ? error.message : "操作未完成，请重试。"); return null; }
    finally { finishWriting(); }
  }
  async function runSelfCheck(task: VillageTask, answer: string) {
    const current = currentTasks.current.find(row => row.id === task.id) ?? task;
    if (!enabled || writing.current || !isAiAssessment(task) || !isAiAssessment(current)
        || current.versionId !== task.versionId || !canOpenExplorationTask(current)
        || !["active", "returned"].includes(current.status)) return null;
    const identity = JSON.stringify([task.id, task.versionId, answer]);
    const request = selfCheckRequests.current.get(identity) ?? { key: crypto.randomUUID(), revision: task.revision };
    selfCheckRequests.current.set(identity, request);
    setSelfCheckState(previous => ({
      taskId: task.id, versionId: task.versionId, pending: true,
      ...(previous?.taskId === task.id && previous.versionId === task.versionId ? { items: previous.items } : {}),
    }));
    beginWriting();
    try {
      const response = await fetch("/api/learner/exploration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command: "selfCheck", taskId: task.id, versionId: task.versionId, revision: request.revision, key: request.key, answer }) });
      const result = await response.json();
      if (!response.ok) {
        // A rejected request can be retried with a fresh catalog revision. Network
        // failures and 5xx responses may follow a side effect, so retain that key.
        if (response.status >= 400 && response.status < 500) selfCheckRequests.current.delete(identity);
        throw new Error(failureMessage(result.error, "自测未完成，请查看历史记录后重试。"));
      }
      const updated = result as { record: ExplorationSelfCheckRecord; items: ExplorationSelfCheckRecord[]; task: VillageTask };
      if (updated.task?.id !== task.id || !updated.record?.id || !Array.isArray(updated.items)) throw new Error("暂未确认自测结果，请读取历史记录核对后重试。");
      // Keep an unconfirmed request's key so a network retry only retrieves its result.
      // An explicit completed/failed attempt may start a new check and retain history.
      if (updated.record.status !== "RUNNING" && !["PENDING", "UNCERTAIN"].includes(updated.record.commentStatus ?? "")) selfCheckRequests.current.delete(identity);
      setSelfCheckState({ taskId: task.id, versionId: task.versionId, pending: true, items: updated.items });
      replaceTask(updated.task);
      if (updated.task.status === "completed") {
        try {
          const catalogResponse = await fetch("/api/learner/exploration", { cache: "no-store" });
          const catalog = await catalogResponse.json();
          if (!catalogResponse.ok || !Array.isArray(catalog.items)) throw new Error("任务目录暂未更新");
          // Keep the authoritative completed task even if a replica's catalog is stale.
          const freshTasks = catalog.items as VillageTask[];
          currentTasks.current = freshTasks.some(row => row.id === updated.task.id)
            ? freshTasks.map(row => row.id === updated.task.id ? updated.task : row)
            : [...freshTasks, updated.task];
          setTasks(currentTasks.current);
          if (catalog.treasures) setTreasures(catalog.treasures);
        } catch {
          setError("评测结果已保存，任务目录暂未刷新，请重新读取任务状态。");
        }
      }
      return updated;
    } catch (error) { setError(error instanceof Error ? error.message : "自测未完成，请查看历史记录后重试。"); return null; }
    finally {
      setSelfCheckState(previous => previous?.taskId === task.id && previous.versionId === task.versionId
        ? { ...previous, pending: false } : previous);
      finishWriting();
    }
  }
  async function acknowledgeTreasure(id: string) {
    if (!enabled || writing.current) return false;
    beginWriting();
    try {
      const response = await fetch("/api/learner/exploration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command: "ackTreasure", id, key: crypto.randomUUID() }) });
      const result = await response.json();
      if (!response.ok) throw new Error(failureMessage(result.error, "宝藏已保留，暂时无法更新展示状态，请重试。"));
      if (!result.treasures || !Array.isArray(result.treasures.items) || !Array.isArray(result.treasures.pendingDrops)) throw new Error("暂未确认宝藏状态，请重试。");
      setTreasures(result.treasures);
      return true;
    } catch (error) { setError(error instanceof Error ? error.message : "宝藏状态更新失败，请重试。"); return false; }
    finally { finishWriting(); }
  }
  async function unlockGraduation() {
    if (!enabled || writing.current) return false;
    beginWriting();
    try {
      const response = await fetch("/api/learner/exploration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command: "unlockGraduation", key: crypto.randomUUID() }) });
      const result = await response.json();
      if (!response.ok) throw new Error(failureMessage(result.error, "毕业码暂时无法解锁，请重试。"));
      if (!Array.isArray(result.treasures?.items) || !Array.isArray(result.treasures?.pendingDrops) || result.treasures.graduation?.status !== "READY" || typeof result.treasures.graduation.code !== "string" || !result.treasures.graduation.code.trim()) throw new Error("暂未确认毕业码，请重试解锁。");
      setTreasures(result.treasures);
      return true;
    } catch (error) { setError(error instanceof Error ? error.message : "毕业码解锁失败，请重试。"); return false; }
    finally { finishWriting(); }
  }
  function learningCommand(task: VillageTask, command: "readMaterial" | "completeLearning", extra: { index?: number; checkinConfirmed?: boolean } = {}): Promise<VillageTask | null> {
    const operation = learningQueue.current.catch(() => {}).then(async () => {
      while (writing.current) await writingFinished.current;
      if (!enabled) return null;
      const latest = currentTasks.current.find(row => row.id === task.id) ?? task;
      if (latest.versionId !== task.versionId || !canOpenExplorationTask(latest)) return null;
      if (latest.status === "completed" || (command === "readMaterial" && latest.openedMaterials?.includes(extra.index!))) return latest;
      beginWriting();
      try {
        const response = await fetch("/api/learner/exploration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command, taskId: latest.id, versionId: latest.versionId, revision: latest.revision, key: crypto.randomUUID(), ...extra }) });
        const result = await response.json();
        if (!response.ok) throw new Error(failureMessage(result.error, command === "readMaterial" ? "材料打开记录暂未保存，请重试。" : "任务暂未完成，请重试。"));
        const updated = (result.data ?? result) as VillageTask;
        if (updated.id !== task.id) throw new Error("任务状态未能更新，请刷新后重试。");
        replaceTask(updated);
        if (command === "completeLearning") {
          try {
            const collectionResponse = await fetch("/api/learner/exploration?treasures=1", { cache: "no-store" });
            const collection = await collectionResponse.json();
            if (collectionResponse.ok && collection.treasures) setTreasures(collection.treasures);
          } catch { /* The completed task stays saved; the next catalog refresh restores the collection. */ }
        }
        return updated;
      } catch (failure) { setError(failure instanceof Error ? failure.message : "任务操作未完成，请重试。"); return null; }
      finally { finishWriting(); }
    });
    learningQueue.current = operation;
    return operation;
  }
  function readMaterial(task: VillageTask, index: number) {
    const requestId = `${task.id}:${task.versionId}:${index}`;
    const pending = materialRequests.current.get(requestId);
    if (pending) return pending;
    const operation = learningCommand(task, "readMaterial", { index }).finally(() => { materialRequests.current.delete(requestId); });
    materialRequests.current.set(requestId, operation);
    return operation;
  }
  const completeLearning = (task: VillageTask, checkinConfirmed = false) => learningCommand(task, "completeLearning", { checkinConfirmed });
  return { tasks, loading, error, busy, selfCheckState, refresh, mutate, runSelfCheck, readMaterial, completeLearning, treasures, acknowledgeTreasure, unlockGraduation };
}

function TaskSymbol({ index = 0 }: { index?: number }) {
  return <span className={`ex-task-symbol ex-task-symbol-${index % 3}`} aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M8 5h12l5 5v17H8V5Z" stroke="currentColor" strokeWidth="1.5" /><path d="M20 5v6h5M12 15h9M12 19h9M12 23h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg></span>;
}
function TaskStatus({ task }: { task: VillageTask }) {
  const label = explorationStatusLabels[task.status] ?? "待解锁";
  return <span className="ex-status" data-status={task.status}><i />{label}</span>;
}
function actionLabel(task: VillageTask) {
  if (task.status === "locked") return "等待上一任务提交";
  if (task.status === "unavailable") return "暂不可用";
  return task.status === "available" ? "查看并接取" : task.status === "active" ? "继续任务" : task.status === "returned" ? isAiAssessment(task) ? "修改并重测" : "修改并重交" : task.status === "pending" ? "查看提交" : "查看成果";
}

export function ExplorationAiAssessmentActions({ task, answer, busy, selfCheckPending, selfCheckRecords, savedMessage, hasNext, actionsContainer, onAnswer, onAction, onRun, onContinue }: {
  task: VillageTask;
  answer: string;
  busy: boolean;
  selfCheckPending?: boolean;
  selfCheckRecords?: ExplorationSelfCheckRecord[];
  savedMessage: string;
  hasNext: boolean;
  actionsContainer?: HTMLElement | null;
  onAnswer: (answer: string) => void;
  onAction: (command: VillageTaskCommand) => Promise<boolean>;
  onRun: () => Promise<{ record: ExplorationSelfCheckRecord; items: ExplorationSelfCheckRecord[] } | null>;
  onContinue: () => void;
}) {
  const editable = task.status === "active" || task.status === "returned";
  const completed = task.status === "completed";
  const renderActions = (actions: ReactNode) => actionsContainer ? createPortal(actions, actionsContainer) : actions;
  if (needsExplorationClaim(task)) return <div className="ex-claim-section"><p>先开始任务并阅读材料，完成作答后运行 AI 评测。达到通过线后自动完成任务。</p>{renderActions(<button type="button" className="module-primary" disabled={busy} onClick={() => void onAction("claim")}>{busy ? "正在准备…" : "开始任务 →"}</button>)}</div>;
  return <div className="ex-ai-assessment-actions">
    <label className="module-field">任务成果或飞书文档链接<textarea rows={5} maxLength={8000} value={answer}
      disabled={busy || !editable} onChange={event => onAnswer(event.target.value)}
      placeholder="填写你的作答，或粘贴飞书结果文档链接；链接旁可以补充说明。完成后运行 AI 评测。" /></label>
    <ExplorationSelfCheck key={`${task.id}:${task.versionId}`} task={task} answer={answer} busy={busy} pending={selfCheckPending} records={selfCheckRecords} onRun={onRun} />
    {completed && <p className="ex-self-check-hint" role="status">任务已完成，评测及完成记录已保存，可以继续下一板块。</p>}
    {renderActions(<>
      {savedMessage && <p className="village-draft-feedback" role="status">✓ {savedMessage}</p>}
      <div className="village-task-actions">
        {editable && <button type="button" className="module-secondary" disabled={busy} onClick={() => { if (!busy && editable) void onAction("draft"); }}>保存草稿</button>}
        {completed && <button type="button" className="module-primary" disabled={busy} onClick={onContinue}>{hasNext ? "进入下一板块 →" : "返回任务目录，查看毕业码 →"}</button>}
      </div>
    </>)}
  </div>;
}

export function ExplorationTaskHall({ searchQuery = "", initialTaskId, initialVariant = "cards", initialTab = "all", scope, onScopeChange, onTaskCountChange, onClearSearch,
  detailOnly = false, sharedExploration, onTaskClose, onTaskBlocked, openFeedback = false, suspended = false, continuationReady = true, onTransitionBusyChange }: {
  searchQuery?: string;
  initialTaskId?: string;
  initialVariant?: ExplorationLayout;
  initialTab?: "all" | "mine";
  scope?: "all" | "mine";
  onScopeChange?: (scope: "all" | "mine") => void;
  onTaskCountChange?: (count: number) => void;
  onClearSearch?: () => void;
  detailOnly?: boolean;
  sharedExploration?: ReturnType<typeof useExplorationTasks>;
  onTaskClose?: () => void;
  onTaskBlocked?: () => void;
  openFeedback?: boolean;
  suspended?: boolean;
  continuationReady?: boolean;
  onTransitionBusyChange?: (busy: boolean) => void;
}) {
  const standaloneExploration = useExplorationTasks(!sharedExploration);
  const exploration = sharedExploration ?? standaloneExploration;
  const { tasks } = exploration;
  const [layout, setLayout] = useState<ExplorationLayout>(initialVariant);
  const [tab, setTab] = useState<"all" | "mine">(initialTab);
  const currentTab = scope ?? tab;
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(initialTaskId ?? null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [savedTaskId, setSavedTaskId] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [continuation, setContinuation] = useState<{ task: VillageTask } | null>(null);
  useLayoutEffect(() => {
    onTransitionBusyChange?.(advancing);
    return () => { onTransitionBusyChange?.(false); };
  }, [advancing, onTransitionBusyChange]);
  const taskBusy = exploration.busy || advancing || suspended;
  const canCloseTask = !suspended && !advancing && (!exploration.busy || exploration.selfCheckState?.pending === true);
  const dialog = useRef<HTMLDialogElement>(null);
  const feedback = useRef<HTMLElement>(null);
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(null);
  const selectedTask = tasks.find(task => task.id === selectedId);
  const selected = selectedTask && canOpenExplorationTask(selectedTask) ? selectedTask : null;
  const feedbackAvailable = !!selected?.feedback;
  const dialogReady = useCanvasDialogBounds(dialog, !!selected && !suspended);
  const selectedMode = selected?.completionMode ?? "assessment";
  const selectedAi = !!selected && isAiAssessment(selected);
  const selectedSelfCheck = selected && exploration.selfCheckState?.taskId === selected.id
    && exploration.selfCheckState.versionId === selected.versionId ? exploration.selfCheckState : null;
  const selectedFeedbackAi = selected?.feedback?.source === "AI" || (!selected?.feedback?.source && selectedAi);
  const selectedAssessmentHref = assessmentHref(selected?.assessmentUrl);
  const taskFileCount = selectedMode === "assessment" ? selected?.taskFiles?.length ?? 0 : 0;
  const selectedIdRef = useRef(selectedId);
  useLayoutEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);
  const orderedTasks = [...tasks].sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));
  const followingTask = selected ? orderedTasks[orderedTasks.findIndex(task => task.id === selected.id) + 1] : undefined;
  const completed = tasks.filter(task => task.status === "completed").length;
  const mine = tasks.filter(isVillageTaskClaimed);
  const inProgress = tasks.filter(task => ["active", "returned"].includes(task.status));
  const pending = tasks.filter(task => task.status === "pending").length;
  const progress = tasks.length ? Math.round(completed / tasks.length * 100) : 0;
  const nextTask = inProgress[0] ?? tasks.find(task => task.status === "available") ?? tasks.find(canOpenExplorationTask);
  const allCompleted = tasks.length > 0 && completed === tasks.length;
  const search = `${searchQuery} ${query}`.trim().toLowerCase();
  const visible = tasks.filter(task => (currentTab !== "mine" || isVillageTaskClaimed(task)) && (filter === "all" || task.status === filter) && (!search || `${task.title} ${task.description}`.toLowerCase().includes(search)));

  useEffect(() => { const timer = window.setTimeout(() => setLayout(initialVariant), 0); return () => clearTimeout(timer); }, [initialVariant]);
  useEffect(() => { const timer = window.setTimeout(() => { setTab(initialTab); setFilter("all"); }, 0); return () => clearTimeout(timer); }, [initialTab]);
  useEffect(() => { const timer = window.setTimeout(() => setFilter("all"), 0); return () => clearTimeout(timer); }, [scope]);
  useEffect(() => { onTaskCountChange?.(mine.length); }, [mine.length, onTaskCountChange]);
  useEffect(() => {
    if (!initialTaskId || selectedIdRef.current === initialTaskId) return;
    selectedIdRef.current = initialTaskId;
    setContinuation(null);
    setSelectedId(initialTaskId);
  }, [initialTaskId]);
  useEffect(() => {
    if (!selectedTask || canOpenExplorationTask(selectedTask)) return;
    const timer = window.setTimeout(() => {
      selectedIdRef.current = null;
      setSelectedId(null);
      onTaskBlocked?.();
      onTaskClose?.();
    }, 0);
    return () => clearTimeout(timer);
  }, [selectedTask?.id, selectedTask?.status, onTaskBlocked, onTaskClose]);
  useEffect(() => {
    const element = dialog.current;
    if (selected && !suspended && dialogReady && element && !element.open) element.showModal();
    if ((!selected || suspended || !dialogReady) && element?.open) element.close();
  }, [selected?.id, suspended, dialogReady]);
  useEffect(() => {
    const body = dialog.current?.querySelector<HTMLElement>(".ex-detail-scroll");
    if (body) body.scrollTop = 0;
  }, [selected?.id]);
  useEffect(() => {
    if (!openFeedback || !dialogReady || selected?.id !== initialTaskId || !feedbackAvailable) return;
    feedback.current?.scrollIntoView({ block: "center" });
    feedback.current?.focus({ preventScroll: true });
  }, [openFeedback, dialogReady, selected?.id, selected?.feedback?.at, initialTaskId, feedbackAvailable]);

  function changeLayout(next: ExplorationLayout) {
    setLayout(next);
    const url = new URL(window.location.href);
    url.searchParams.set("variant", next);
    window.history.replaceState(null, "", url);
  }
  function openTask(task: VillageTask) { if (canOpenExplorationTask(task)) { setContinuation(null); selectedIdRef.current = task.id; setSelectedId(task.id); setNotice(""); setSavedTaskId(null); } }
  function changeTab(next: "all" | "mine") { setTab(next); onScopeChange?.(next); setFilter("all"); }
  const closeTask = useCallback(() => { if (canCloseTask) { selectedIdRef.current = null; setContinuation(null); setSelectedId(null); setNotice(""); onTaskClose?.(); } }, [canCloseTask, onTaskClose]);
  const continueAfter = useCallback((task: VillageTask, latestTasks = tasks) => {
    if (suspended) return;
    const ordered = [...latestTasks].sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));
    const next = ordered[ordered.findIndex(row => row.id === task.id) + 1];
    if (next && !canOpenExplorationTask(next)) { setNotice("需要提交上一任务"); return; }
    if (next) {
      selectedIdRef.current = next.id; setSelectedId(next.id); setNotice(""); setSavedTaskId(null);
      const body = dialog.current?.querySelector<HTMLElement>(".ex-detail-scroll");
      if (body) body.scrollTop = 0;
    } else closeTask();
  }, [tasks, suspended, closeTask]);
  useEffect(() => {
    if (!continuation) return;
    const obsolete = selectedIdRef.current !== continuation.task.id || selected?.id !== continuation.task.id || selected.versionId !== continuation.task.versionId;
    if (!obsolete && (advancing || exploration.busy || suspended || !continuationReady)) return;
    // Defer the state transition until after the current dialog commit. A change
    // to the selected task or treasure presentation cancels this transition.
    const timer = window.setTimeout(() => {
      setContinuation(null);
      if (obsolete || selectedIdRef.current !== continuation.task.id) return;
      continueAfter(continuation.task);
    }, 0);
    return () => clearTimeout(timer);
  }, [continuation, selected?.id, selected?.versionId, advancing, exploration.busy, suspended, continuationReady, continueAfter]);
  async function finishLearning(task: VillageTask, checkinConfirmed: boolean) {
    if (taskBusy) return false;
    setAdvancing(true);
    try {
      const updated = await exploration.completeLearning(task, checkinConfirmed);
      if (!updated) return false;
      const latestTasks = await exploration.refresh();
      if (selectedIdRef.current === task.id) {
        if (latestTasks) setContinuation({ task: updated });
        else setNotice("完成记录已保存，任务状态暂未刷新，请稍后重试。");
      }
      return true;
    } finally { setAdvancing(false); }
  }
  async function act(task: VillageTask, command: VillageTaskCommand) {
    if (taskBusy || command === "cancel" || !canOpenExplorationTask(task)) return false;
    setAdvancing(true);
    try {
      const updated = await exploration.mutate(task, command, answers[task.id] ?? task.answer ?? "");
      if (!updated) return false;
      if (command === "claim") setNotice(isAiAssessment(task) ? "任务已接取。阅读材料并作答，AI 评测达标后自动完成。" : "任务已接取。阅读材料后，完成任务并提交审核。");
      if (command === "draft") { setNotice("草稿保存成功"); setSavedTaskId(task.id); }
      if (command === "submit") { setNotice("提交成功。审核结果会在任务详情中显示。"); setSavedTaskId(null); }
      if (command === "submit") await exploration.refresh();
      return true;
    } finally { setAdvancing(false); }
  }

  return <section className={detailOnly ? "exploration-task-dialog-host" : "exploration-task-hall"} aria-label={detailOnly ? "探索任务操作" : "探索营任务大厅"} data-layout={layout}>
    {!detailOnly && <>
    <header className="ex-heading"><div><span className="ex-eyebrow">YOUR FIRST CHAPTER AT MUCHEN</span><h1>探索营</h1><p>从理解沐晨开始，找到自己的位置。</p></div><div className="ex-layout-picker" role="group" aria-label="探索营版式预览"><span>版式预览</span>{layouts.map(item => <button type="button" key={item.id} aria-pressed={layout === item.id} onClick={() => changeLayout(item.id)} title={item.description}><b>{item.letter}</b>{item.title}</button>)}</div></header>

    <section className="ex-welcome-grid" aria-label="探索营学习概览">
      <div className="ex-hero"><div className="ex-hero-copy"><span className="ex-eyebrow">EXPLORE · LEARN · BELONG</span><h2>每一次探索，<br />都让你更靠近沐晨。</h2><p>选择一份任务，阅读材料、留下思考，<br />让理解成为行动的起点。</p><button className="ex-primary" type="button" disabled={!nextTask || exploration.loading} onClick={() => nextTask && openTask(nextTask)}>{allCompleted ? "回顾我的探索" : inProgress.length ? "继续我的探索" : "开始第一份任务"}<span aria-hidden="true">↗</span></button></div><div className="ex-orbit" aria-hidden="true"><i /><i /><i /><span className="ex-orbit-star">✦</span><div className="ex-orbit-core"><span>MUCHEN</span><strong>JOURNEY</strong><small>你的下一种可能</small></div><span className="ex-orbit-dot" /><span className="ex-orbit-label">A BRIGHTER YOU</span></div></div>
      <div className="ex-progress-card"><div className="ex-progress-heading"><span>我的探索进度</span><strong>{completed}<small> / {tasks.length}</small></strong></div><div className="ex-progress-track" role="progressbar" aria-label="探索任务完成进度" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={tasks.length || 1}><span style={{ width: `${progress}%` }} /></div><p>学习板块学完即完成；AI 任务评测达标后完成，人工审核任务审核通过后完成。</p><div className="ex-progress-numbers"><div><strong>{inProgress.length}</strong><span>进行中</span></div><div><strong>{pending}</strong><span>待审核</span></div><div><strong>{completed}</strong><span>已完成</span></div></div><div className="ex-process"><span>打开学习</span><i>→</i><span>完成板块</span><i>→</i><span>解锁毕业码</span></div></div>
    </section>

    <section className="ex-catalog" aria-labelledby="ex-catalog-title">
      <div className="ex-catalog-heading"><div className="ex-tabs" role="tablist" aria-label="探索任务范围"><button type="button" role="tab" aria-selected={currentTab === "all"} onClick={() => changeTab("all")}>全部任务 <span>{tasks.length}</span></button><button type="button" role="tab" aria-selected={currentTab === "mine"} onClick={() => changeTab("mine")}>我的任务 <span>{mine.length}</span></button></div><button type="button" className="ex-text-button" onClick={() => void exploration.refresh()} disabled={exploration.busy}>刷新任务 <span aria-hidden="true">↻</span></button></div>
      <div className="ex-filter-row"><div className="ex-status-filters" role="group" aria-label="探索任务状态筛选">{([['all', '全部状态'], ['locked', '待解锁'], ['active', '进行中'], ['pending', '待审核'], ['returned', '待修改'], ['completed', '已完成']] as const).map(([value, label]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div><label className="ex-search"><span aria-hidden="true">⌕</span><input type="search" aria-label="搜索探索任务" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索任务名称或介绍" /></label></div>
      <div className="ex-list-heading"><h2 id="ex-catalog-title">{currentTab === "mine" ? "继续你的学习旅程" : layout === "path" ? "探索顺序，由你决定" : layout === "list" ? "把每一份理解，写进清单" : "为你的第一程，准备好了"}</h2><span>{visible.length} 个任务{layout === "path" ? " · 按顺序解锁任务" : " · 按后台排序排列"}</span></div>

      {exploration.error && <div className="ex-error" role="alert"><span>{exploration.error}</span><button type="button" onClick={() => void exploration.refresh()}>重新读取</button></div>}
      {exploration.loading ? <div className="ex-empty" role="status"><span className="ex-loading-ring" /><h3>正在准备你的探索任务…</h3><p>很快就能开始新的学习。</p></div> : !visible.length ? <div className="ex-empty"><TaskSymbol /><h3>{tasks.length ? "暂时没有符合条件的任务" : "新的探索，正在准备中"}</h3><p>{tasks.length ? "试试其他状态，或调整搜索关键词。" : "任务发布后，会在这里与你见面。"}</p>{tasks.length > 0 && <button className="ex-secondary" type="button" onClick={() => { setFilter("all"); setQuery(""); changeTab("all"); onClearSearch?.(); }}>查看全部任务</button>}</div> : <div className={`ex-task-collection ex-task-collection-${layout}`}>
        {visible.map((task, index) => <article className="ex-task-card" key={task.id} data-status={task.status}>
          <div className="ex-card-top"><span className="ex-task-order">{String(tasks.indexOf(task) + 1).padStart(2, "0")}</span><TaskStatus task={task} /></div>
          <div className="ex-card-content"><TaskSymbol index={index} /><div className="ex-card-copy"><h3><button type="button" disabled={!canOpenExplorationTask(task)} onClick={() => openTask(task)}>{task.title}</button></h3><p>{task.description}</p></div></div>
          <div className="ex-card-meta"><span>{task.review || "人工审核"}</span><span>{task.materials?.length || 0} 份学习材料</span></div>
          <div className="ex-card-footer"><span>{task.status === "completed" ? "这一站，已留下你的足迹" : task.status === "pending" ? "你的成果已送达审核人" : task.status === "returned" ? "收到反馈，准备更好的答案" : task.mentor ? `${task.mentor} · 任务发布人` : "每一步探索，都算数"}</span><button type="button" className="ex-task-action" disabled={!canOpenExplorationTask(task)} onClick={() => openTask(task)}>{actionLabel(task)} <span aria-hidden="true">→</span></button></div>
        </article>)}
      </div>}
      <footer className="ex-catalog-footer"><span>MUCHEN JOURNEY</span><p>成长不止一条路线，每一步探索，都算数。</p><span>EXPLORE YOUR NEXT POSSIBILITY</span></footer>
    </section>

    </>}
    <dialog ref={dialog} className="exploration-task-modal" aria-labelledby="ex-task-detail-title" onCancel={event => { if (!canCloseTask) event.preventDefault(); else closeTask(); }} onClick={event => { if (event.target === event.currentTarget) closeTask(); }}>
      <div className="module-dialog journey-dialog exploration-task-dialog"><JourneyDialogSurface>
      <header className="ex-detail-header"><div className="ex-detail-heading"><span className="ex-eyebrow">探索营 / 任务详情</span><button type="button" aria-label="关闭探索任务详情" disabled={!canCloseTask} onClick={closeTask}>关闭 ×</button></div>{selected && <><div className="ex-detail-topline"><TaskStatus task={selected} /></div><h2 id="ex-task-detail-title">{selected.title}</h2></>}</header>
      <div className="ex-detail-scroll" role="region" aria-label="任务详情内容，可向下滚动" tabIndex={0}>{selected && <>
        <p className="ex-detail-description">{selected.description}</p><div className="ex-detail-meta"><span>{selectedMode === "learning" ? "学习完成后直接记录" : selectedMode === "checkin" ? "完成签退及入群后确认" : selected.review || "人工审核"}</span><span>{selected.materials?.length || 0} 份学习材料</span></div>
        {selectedMode === "assessment" && (selected.assessmentUrl || !taskFileCount) && (selectedAi
          ? <div className="ex-assessment-entry"><div><span>培训测试 · AI 评测</span><h3>完成作答，评测达标后自动完成</h3><p>{selectedAssessmentHref ? "测试将在新页面打开。完成后返回这里，填写成果或飞书文档链接，运行 AI 评测。" : "请根据任务要求完成作答，AI 将按本任务的评分维度和参考答案评测。"}</p></div>{selectedAssessmentHref && <a className="module-primary" href={selectedAssessmentHref} target="_blank" rel="noopener noreferrer" onClick={needsExplorationClaim(selected) ? () => { void act(selected, "claim"); } : undefined}>进入测试 ↗</a>}</div>
          : <ExplorationAssessmentEntry url={selected.assessmentUrl} onStart={needsExplorationClaim(selected) ? () => { void act(selected, "claim"); } : undefined} />)}
        <section className="ex-detail-section"><h3><span>01</span>{selectedMode === "checkin" ? "签退与入群材料" : "学习材料"} · {selected.materials?.length || 0} 份</h3><p>{selectedMode === "learning" ? "打开每份材料后，完成下方确认即可进入下一板块，无需提交学习心得。" : selectedMode === "checkin" ? "请按任务说明完成签退及入群，二维码图片会直接显示在下方。" : selectedAi ? "先查看学习材料，完成任务作答后运行 AI 评测，达到通过线后自动完成。" : taskFileCount ? "先查看学习材料，再打开下方任务文件完成作答，提交任务成果供审核。" : "查看下列材料，完成测试后提交测试结果。"}</p><ul className="ex-materials">{selected.materials?.map((material, index) => <ExplorationLearningMaterial key={`${selected.id}:${selected.versionId}:${index}:${material.name}`} taskId={selected.id} index={index} material={material} opened={selected.openedMaterials?.includes(index)} onOpened={selectedMode !== "assessment" && selected.status !== "completed" ? () => exploration.readMaterial(selected, index) : undefined} />)}{!selected.materials?.length && <li><p>{selectedMode === "checkin" ? "本任务暂未配置二维码，请根据任务说明完成签退及入群；管理员补充图片后会在这里显示。" : "本板块暂未配置附件，请阅读下方任务说明。"}</p></li>}</ul></section>
        {taskFileCount > 0 && <section className="ex-detail-section ex-task-files-section"><h3><span>02</span>任务文件 · {taskFileCount} 份</h3><p>这里是管理员发布的题目或作答要求。打开或下载文件，完成后在下方填写任务成果或结果文档链接，{selectedAi ? "运行 AI 评测。" : "提交审核。"}</p>{needsExplorationClaim(selected) ? <div className="ex-claim-section"><button type="button" className="module-primary" disabled={taskBusy} onClick={() => void act(selected, "claim")}>{taskBusy ? "正在准备…" : "开始任务，查看任务文件 →"}</button></div> : <ul className="ex-materials">{selected.taskFiles?.map((material, index) => <ExplorationLearningMaterial key={`${selected.id}:${selected.versionId}:task:${index}:${material.name}`} taskId={selected.id} index={index} material={material} group="task" />)}</ul>}</section>}
        <section className="ex-detail-section"><h3><span>{taskFileCount ? "03" : "02"}</span>任务要求</h3><ol>{selected.requirements?.length ? selected.requirements.map((item, index) => <li key={index}>{item}</li>) : <li>{selectedMode === "learning" ? "阅读本板块材料与说明，完成学习后确认并进入下一板块。" : selectedMode === "checkin" ? "完成签退并进入项目培训群后，勾选确认。" : selectedAi ? "完成任务作答，填写成果或飞书文档链接。AI 按本任务标准评分，达到通过线后自动完成。" : taskFileCount ? "完成任务文件中的题目，并提交任务成果或结果文档链接供审核。" : "完成测试，并提交测试结果或结果文档链接供审核。"}</li>}</ol>{selected.criteria?.length > 0 && <div className="ex-criteria"><strong>完成标准</strong>{selected.criteria.map((item, index) => <p key={index}>✓ {item}</p>)}</div>}</section>
        {selected.feedback && <section ref={feedback} className="ex-review-feedback" tabIndex={-1} aria-label={selectedFeedbackAi ? "AI 评测反馈" : "人工审核反馈"} data-decision={selected.feedback.decision}><strong>{["PASS", "APPROVE"].includes(selected.feedback.decision) ? selectedFeedbackAi ? "AI 评测通过 · 这一步完成了" : "审核通过 · 这一步完成了" : selectedFeedbackAi ? "AI 评测反馈 · 修改后可重新评测" : "审核反馈 · 期待你的进一步完善"}</strong><p>{selected.feedback.text}</p><time>{new Date(selected.feedback.at).toLocaleString("zh-CN")}</time></section>}
        <section className="ex-detail-section ex-submit-section"><h3><span>{taskFileCount ? "04" : "03"}</span>{selectedMode === "learning" ? "完成本板块学习" : selectedMode === "checkin" ? "确认签退与入群" : selectedAi ? "任务成果与 AI 评测" : taskFileCount ? selected.status === "completed" ? "你的任务成果" : "提交任务成果" : selected.status === "completed" ? "你的测试结果" : "提交测试结果"}</h3>{selectedMode === "assessment" ? selectedAi
          ? <ExplorationAiAssessmentActions key={selected.id} task={selected} answer={answers[selected.id] ?? selected.answer ?? ""} busy={taskBusy} selfCheckPending={selectedSelfCheck?.pending} selfCheckRecords={selectedSelfCheck?.items} savedMessage={savedTaskId === selected.id ? "草稿保存成功" : ""} actionsContainer={actionsContainer} hasNext={!!followingTask} onContinue={() => continueAfter(selected)} onAnswer={answer => { setAnswers(previous => ({ ...previous, [selected.id]: answer })); setSavedTaskId(null); }} onRun={() => exploration.runSelfCheck(selected, answers[selected.id] ?? selected.answer ?? "")} onAction={command => act(selected, command)} />
          : <ExplorationAssessmentActions key={`${selected.id}:${selected.status}`} task={selected} answer={answers[selected.id] ?? selected.answer ?? ""} busy={taskBusy} savedMessage={savedTaskId === selected.id ? "草稿保存成功" : ""} actionsContainer={actionsContainer} hasNext={!!followingTask} onContinue={() => continueAfter(selected)} onAnswer={answer => { setAnswers(previous => ({ ...previous, [selected.id]: answer })); setSavedTaskId(null); }} beforeActions={null} onAction={command => act(selected, command)} />
          : <ExplorationLearningActions key={`${selected.id}:${selectedMode}`} task={selected} busy={taskBusy} actionsContainer={actionsContainer} hasNext={!!followingTask} onComplete={confirmed => finishLearning(selected, confirmed)} onContinue={() => continueAfter(selected)} />}</section>
      </>}</div>
      <footer className="ex-detail-footer"><div ref={setActionsContainer} className="ex-detail-actions" />{notice && notice !== "草稿保存成功" && <p className="ex-detail-notice" role="status">{notice}</p>}{exploration.error && <p className="ex-detail-error" role="alert">{exploration.error}</p>}</footer>
      </JourneyDialogSurface></div>
    </dialog>
  </section>;
}
