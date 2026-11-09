import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MedalResponse } from "./badgeEconomy";
import { adaptGuildMedals, guildCanApply, guildPendingRequest, guildSubmission, guildTaskValidation, type GuildSnapshot, type GuildTaskDraft } from "./guildGrowthModel";

type GuildData = { identity: string; snapshot: GuildSnapshot; medals: MedalResponse };
async function readResponse<T>(response: Response, fallback: string): Promise<T> {
  const result = await response.json().catch(() => null);
  if (!response.ok || !result) throw new Error(result?.error || fallback);
  return result as T;
}

export function useGuildGrowth(identity: string, active = true) {
  const [stored, setStored] = useState<GuildData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const sequence = useRef(0);
  const writing = useRef(false);
  const currentIdentity = useRef(identity);
  const mounted = useRef(true);
  const data = stored?.identity === identity ? stored : null;
  const currentData = useRef<GuildData | null>(null);
  useLayoutEffect(() => {
    currentIdentity.current = identity;
    currentData.current = stored?.identity === identity ? stored : null;
  }, [identity, stored]);
  const refresh = useCallback(async () => {
    if (writing.current) return;
    const ticket = ++sequence.current;
    setRefreshing(true);
    try {
      const [snapshot, medals] = await Promise.all([
        fetch("/api/learner/guild", { cache: "no-store" }).then(response => readResponse<GuildSnapshot>(response, "公会认证记录读取失败，请重试。")),
        fetch("/api/learner/medals", { cache: "no-store" }).then(response => readResponse<MedalResponse>(response, "徽章凭证读取失败，请重试。")),
      ]);
      if (mounted.current && ticket === sequence.current && currentIdentity.current === identity) {
        currentData.current = { identity, snapshot, medals };
        setStored(currentData.current); setError("");
      }
    } catch (failure) {
      if (mounted.current && ticket === sequence.current && currentIdentity.current === identity) setError(failure instanceof Error ? failure.message : "公会数据读取失败，请重试。");
    } finally {
      if (mounted.current && ticket === sequence.current) setRefreshing(false);
    }
  }, [identity]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; ++sequence.current; };
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => setError(""), 0); return () => window.clearTimeout(timer); }, [identity]);
  useEffect(() => {
    if (!active) return;
    const initial = window.setTimeout(() => void refresh(), 0);
    const check = () => { if (!document.hidden && !writing.current) void refresh(); };
    const timer = window.setInterval(check, 30000);
    window.addEventListener("focus", check);
    return () => { window.clearTimeout(initial); ++sequence.current; window.clearInterval(timer); window.removeEventListener("focus", check); };
  }, [active, refresh]);

  const mutate = useCallback(async (command: Record<string, unknown>, fallback: string) => {
    if (!currentData.current || writing.current || currentIdentity.current !== identity) return false;
    if (command.command !== "join" && currentData.current.snapshot.joinedGuild !== command.guildId) return false;
    writing.current = true; ++sequence.current; setBusy(true); setError("");
    try {
      const response = await fetch("/api/learner/guild", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(command) });
      const snapshot = await readResponse<GuildSnapshot>(response, fallback);
      if (!mounted.current || currentIdentity.current !== identity) return false;
      if (currentData.current?.identity === identity) currentData.current = { ...currentData.current, snapshot };
      setStored(previous => previous?.identity === identity ? { ...previous, snapshot } : previous);
      return true;
    } catch (failure) {
      if (mounted.current && currentIdentity.current === identity) setError(failure instanceof Error ? failure.message : fallback);
      return false;
    } finally {
      writing.current = false;
      if (mounted.current) { setBusy(false); setRefreshing(false); }
    }
  }, [identity]);
  const join = useCallback(async (guildId: string) => {
    if (!currentData.current?.snapshot.halls.some(hall => hall.id === guildId)) return false;
    return mutate({ command: "join", guildId }, "工会切换失败，请重试。");
  }, [mutate]);
  const saveTask = useCallback(async (guildId: string, level: 1 | 2 | 3, draft: GuildTaskDraft, submit: boolean) => {
    const snapshot = currentData.current?.snapshot;
    if (!snapshot || snapshot.joinedGuild !== guildId || guildPendingRequest(snapshot) || snapshot.level >= level) return false;
    const task = snapshot.tasks.find(item => item.level === level);
    if (!task || !snapshot.requirements.find(item => item.level === level)?.entryEligible) return false;
    const failure = submit ? guildTaskValidation(task, draft) : draft.artifact.length > 6000 ? "任务成果不能超过 6,000 字。" : "";
    if (failure) { setError(failure); return false; }
    return mutate({ command: "task", guildId, level, artifact: draft.artifact, checks: draft.checks, expectedRevision: draft.revision, submit }, submit ? "任务成果提交失败，请重试。" : "草稿保存失败，请重试。");
  }, [mutate]);
  const submit = useCallback(async (guildId: string, level: 1 | 2 | 3, expectedRevision: number) => {
    const snapshot = currentData.current?.snapshot;
    if (!snapshot || snapshot.joinedGuild !== guildId || !guildCanApply(snapshot, level)) return false;
    const submission = guildSubmission(snapshot, guildId, level);
    if (!submission || submission.status !== "submitted" || !Number.isInteger(expectedRevision) || expectedRevision < 1 || submission.revision !== expectedRevision) return false;
    return mutate({ command: "apply", guildId, level, expectedRevision }, "认证申请提交失败，请重试。");
  }, [mutate]);
  return { snapshot: data?.snapshot || null, account: data ? adaptGuildMedals(data.medals) : null, error, busy, refreshing, refresh, join, saveTask, submit };
}
