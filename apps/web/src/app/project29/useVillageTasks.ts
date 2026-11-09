import { useCallback, useEffect, useRef, useState } from "react";
import type { PracticeTask } from "./moduleDemoData";
import type { ModuleStatusName } from "./ModuleShell";

export const VILLAGE_DIRECTIONS = ["产品开发", "数据交付", "技术开发", "PMO", "AI评测", "质量检测", "项目管理", "AI 能力"];
export type VillageTaskCommand = "claim" | "draft" | "submit" | "cancel";
export type VillageTask = PracticeTask & {
  status:ModuleStatusName; versionId:string; assignmentId:string|null; revision:number|null;
  claimed?:boolean;
  answer:string; publishedAt:string; criteria:string[]; reviewMode:string; passScore:number;
  unlockTaskPoints:number;
  publishingDepartment:string;
  rewardAllocations?:{id:string; points:number}[];
  materials:{name:string; type:string; text:string; url:string}[];
  rubric:{id:string; name:string; description:string; points:number}[];
  feedback:{text:string; at:string; decision:string}|null;
};

export function isVillageTaskClaimed(task: Pick<VillageTask, "status" | "claimed">) {
  return task.claimed ?? task.status !== "available";
}

export function useVillageTasks(enabled:boolean) {
  const [tasks, setTasks] = useState<VillageTask[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(enabled);
  const [busy, setBusy] = useState(false);
  const [wallet, setWallet] = useState<{taskPoints:number}|null>(null);
  const writing = useRef(false);
  const sequence = useRef(0);
  const currentTasks = useRef<VillageTask[]>([]);
  const refresh = useCallback(async () => {
    if (!enabled || writing.current) return;
    const current = ++sequence.current;
    try {
      const response = await fetch("/api/learner/village", {cache:"no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "任务读取失败，请重试。");
      if (current === sequence.current) { currentTasks.current = data.items; setTasks(data.items); setWallet(data.wallet ?? null); setError(""); }
    } catch (failure) {
      if (current === sequence.current) setError(failure instanceof Error ? failure.message : "任务读取失败。");
    } finally { if (current === sequence.current) setLoading(false); }
  }, [enabled]);
  useEffect(() => {
    if (!enabled) return;
    const initial = window.setTimeout(() => void refresh(), 0);
    const check = () => { if (!document.hidden) void refresh(); };
    const timer = window.setInterval(check, 30000);
    window.addEventListener("focus", check);
    return () => { window.clearTimeout(initial); ++sequence.current; clearInterval(timer); window.removeEventListener("focus", check); };
  }, [enabled, refresh]);
  async function mutate(task:VillageTask, command:VillageTaskCommand, answer:string) {
    if (!enabled || writing.current) return null;
    if (command === "cancel") {
      const current = currentTasks.current.find(row => row.id === task.id);
      if (task.status !== "active" || !current || current.status !== "active" || current.revision !== task.revision) {
        setError("只有进行中的任务可以取消接取，请刷新任务状态后重试。");
        return null;
      }
    }
    writing.current = true; ++sequence.current; setBusy(true); setError("");
    try {
      const response = await fetch("/api/learner/village", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({command, taskId:task.id, versionId:task.versionId, revision:task.revision,
          key:crypto.randomUUID(), ...(command === "cancel" ? {} : {answer})})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "操作未完成，请重试。");
      currentTasks.current = currentTasks.current.map(row => row.id === task.id ? data : row);
      setTasks(currentTasks.current);
      return data as VillageTask;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "操作未完成，请重试。");
      return null;
    } finally { writing.current = false; setBusy(false); }
  }
  return {tasks, error, loading, busy, refresh, mutate, wallet};
}
