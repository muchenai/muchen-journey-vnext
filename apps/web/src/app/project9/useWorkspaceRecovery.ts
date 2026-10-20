"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { saveSubmissionDraft, type AISelfCheckRecord } from "../actions";
import type { ProjectExperienceData } from "../project-ui/types";
import { readWorkspace, selfCheckRecovery, workspaceKey } from "./workspace-recovery";

export function useWorkspaceRecovery(experience: ProjectExperienceData | null, enabled: boolean) {
  const canSubmit = Boolean(experience?.allowedCommands.some(command => command.startsWith("submit")));
  const initialBody = canSubmit ? experience?.draftBody || experience?.latestSubmissionBody || "" : experience?.latestSubmissionBody || "";
  const key = experience ? workspaceKey(experience.assignmentId, experience.taskVersion, experience.revision) : "";
  const [record, setRecord] = useState(initialBody);
  const bodyRef = useRef(initialBody);
  const [readyKey, setReadyKey] = useState("");
  const savedBody = useRef(experience?.draftBody ?? "");
  const pendingSince = useRef<number | null>(null);
  const requestInFlight = useRef(false);
  const selfCheckInFlight = useRef(Boolean(experience));
  const [selfCheckBusy, setSelfCheckBusy] = useState(false);
  const [selfCheckRecovering, setSelfCheckRecovering] = useState(Boolean(experience));
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const sawActive = useRef(false);
  const persist = useCallback((body: string) => {
    if (!key || !canSubmit) return;
    try { localStorage.setItem(key, JSON.stringify({ body, pendingSince: pendingSince.current })); }
    catch { setSaveError("浏览器暂时无法保存草稿，正在尝试保存到服务器。"); }
  }, [key, canSubmit]);
  const updateRecord = useCallback((body: string) => {
    bodyRef.current = body;
    setRecord(body);
    persist(body); // Synchronous: a quick Back/refresh must not lose new input.
  }, [persist]);

  useEffect(() => {
    let cached = null;
    try { cached = key && canSubmit ? readWorkspace(localStorage, key) : null; } catch { /* Server draft remains available. */ }
    const body = cached ? cached.body : initialBody;
    bodyRef.current = body;
    // Hydrate browser-only persisted input after SSR; this is external storage,
    // not state derived from the current render's props.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecord(body);
    pendingSince.current = cached?.pendingSince ?? null;
    savedBody.current = experience?.draftBody ?? "";
    setReadyKey(key);
    // Only reset on entering a different task/edit revision, not on draft revalidation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, canSubmit]);

  useEffect(() => {
    if (!experience || !enabled || readyKey !== key || !canSubmit || selfCheckBusy || selfCheckRecovering || record === savedBody.current) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      const data = new FormData();
      data.set("assignment_id", experience.assignmentId);
      data.set("revision", String(experience.revision));
      data.set("draft_idempotency_key", crypto.randomUUID());
      data.set("body", record);
      data.set("evidence_url", "");
      try {
        const result = await saveSubmissionDraft({}, data);
        if (cancelled) return;
        if (result.error) setSaveError(`草稿已保留在本机，服务器保存失败：${result.error}`);
        else { savedBody.current = record; setSaveError(""); }
      } catch { if (!cancelled) setSaveError("草稿已保留在本机，服务器保存暂未成功。"); }
    }, 1200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [record, key, readyKey, canSubmit, selfCheckBusy, selfCheckRecovering, enabled, experience]);

  useEffect(() => {
    if (!experience || !enabled || readyKey !== key) return;
    let cancelled = false;
    let timer: number;
    let controller: AbortController | null = null;
    const poll = async () => {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 10_000);
      try {
        const response = await fetch(`/api/learner/tasks/${experience.assignmentId}/self-checks`, { cache: "no-store", signal: controller.signal });
        const data = await response.json() as { records?: AISelfCheckRecord[]; error?: string };
        if (cancelled) return;
        if (!response.ok || !data.records) throw new Error(data.error || "无法查询自查状态。");
        const state = selfCheckRecovery(data.records, pendingSince.current);
        // Recover older sessions that started a check before autosave existed.
        let cached = null;
        try { cached = key ? readWorkspace(localStorage, key) : null; } catch { /* optional local cache */ }
        if (canSubmit && !bodyRef.current && !cached && state.newest?.body) updateRecord(state.newest.body);
        const busy = requestInFlight.current || state.busy;
        selfCheckInFlight.current = busy;
        setSelfCheckBusy(busy);
        setSelfCheckRecovering(false);
        if (state.active) sawActive.current = true;
        if (busy) setWorkspaceMessage(state.active?.status === "SENDING" ? "AI 评价已生成，正在同步飞书评论…" : "AI 自查中，可以离开页面，返回后会自动恢复状态。");
        else {
          if (sawActive.current && state.newest?.status === "COMPLETED") setWorkspaceMessage("AI 自查已完成，可查看历史评价后提交任务。");
          else if (state.newest && ["FAILED", "UNCERTAIN"].includes(state.newest.status)) setWorkspaceMessage(state.newest.result);
          else setWorkspaceMessage("");
          pendingSince.current = null;
          persist(bodyRef.current);
          sawActive.current = false;
        }
      } catch (error) {
        if (!cancelled) setWorkspaceMessage(error instanceof Error && error.name !== "AbortError" ? error.message : "正在重新查询 AI 自查状态，请稍候…");
      } finally {
        window.clearTimeout(timeout);
        if (!cancelled) timer = window.setTimeout(poll, 3000);
      }
    };
    void poll();
    return () => { cancelled = true; controller?.abort(); window.clearTimeout(timer); };
  }, [experience?.assignmentId, enabled, key, readyKey, canSubmit, persist, updateRecord]);

  const beginSelfCheck = () => {
    requestInFlight.current = selfCheckInFlight.current = true;
    pendingSince.current = Date.now();
    persist(bodyRef.current);
    setSelfCheckBusy(true);
    sawActive.current = true;
  };
  const finishSelfCheck = () => {
    requestInFlight.current = false;
    pendingSince.current = null;
    persist(bodyRef.current);
    // Polling alone releases the controls after confirming the server's state.
  };
  return { record, updateRecord, selfCheckBusy, selfCheckRecovering, selfCheckInFlight, beginSelfCheck, finishSelfCheck,
    workspaceMessage: saveError || workspaceMessage };
}
