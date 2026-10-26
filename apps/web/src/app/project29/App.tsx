"use client";
import "./index.css";
import "./loader.css";
import "./retained-controls.css";

import { FormEvent, MouseEvent, useState, useEffect, useId, useRef, useLayoutEffect, useCallback, CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { effectiveCharacterCount } from "@/lib/text-length";
import { clientLoginErrorMessage, isFeishuClient, loginInsideFeishu } from "@/lib/feishu-client-login";
import { ExecutionDetail, ExecutionView, TaskCards, executionTasks } from "./ExecutionPages";
import { UpdatedDashboard } from "./UpdatedDashboard";
import { ModuleHub } from "./ModuleHub";
import { useCanvasScale } from "./useCanvasScale";
import { SelfCheckHistory } from "./SelfCheckHistory";
import { TaskFeedbackDialog } from "./TaskFeedbackDialog";
import { useWorkspaceRecovery } from "./useWorkspaceRecovery";
import { runAiSelfCheck, type AISelfCheckRecord } from "../actions";
import { JourneyProvider, useJourney, useTaskStatus, type JourneyContextValue } from "./journey-context";
import { ProjectResourceLoader } from "./EntryLoader";
import { logoutSession, recordOpenedLearningMaterial, confirmIdentity, exchangeInvite, saveSubmissionDraft, startAssignment, startEvidenceRevision, cancelEvidenceRevision, submitAssignment, loginWithPassword, registerWithPassword, resetPhonePassword, requestPhoneCode, migrateCompletionCode } from "../actions";
 type Screen = "login" | "welcome" | "dashboard" | "tasks" | "detail" | "view" | "village" | "academy" | "guild";
type PreviewIdentity = string;
export default function App(props: Partial<JourneyContextValue>) {
 const value: JourneyContextValue = { learnerName: "新同学", experience: null, initialScreen: "login", joinPhase: "invite", joinError: "", ...props };
 return <JourneyProvider value={value}><ExperienceScreen /></JourneyProvider>;
}

function ExperienceScreen() {
 const router = useRouter();
 const { learnerName, experience, initialScreen, initialNotice, joinPhase, joinError } = useJourney();
 const taskStatus = useTaskStatus();
 const identity = learnerName;
 const [screen, setScreen] = useState<Screen>(initialScreen);
 const [entryResourcesReady, setEntryResourcesReady] = useState(initialScreen !== "login");
 const scale = useCanvasScale();
 const viewportRef = useRef<HTMLElement>(null);
 const [notice, setNotice] = useState(initialNotice ?? "");
 const [burst, setBurst] = useState<{ x: number; y: number; key: number } | null>(null);
 const { record, updateRecord, selfCheckBusy, selfCheckRecovering, selfCheckInFlight, beginSelfCheck, finishSelfCheck,
   workspaceMessage } = useWorkspaceRecovery(experience, screen === "view" || screen === "detail");
 const [choice, setChoice] = useState("");
 const [checked, setChecked] = useState(false);
 const [historyOpen, setHistoryOpen] = useState(false);
 const [feedbackAssignmentId, setFeedbackAssignmentId] = useState<string | null>(null);
 const selectedFeedback = experience?.reviewFeedback?.find(item => item.assignmentId === feedbackAssignmentId);
 const [historyRecords, setHistoryRecords] = useState<AISelfCheckRecord[]>([]);
 const [historyError, setHistoryError] = useState("");
 const [submitting, setSubmitting] = useState(false);
 const submissionInFlight = useRef(false);
 const [revisionBusy, setRevisionBusy] = useState(false);
 const revisionInFlight = useRef(false);
 const canSubmit = Boolean(experience?.allowedCommands.some(command => command.startsWith("submit")));
 const submissionStatus = experience?.status;
 const submitLabel = selfCheckBusy ? "待 AI 自查完成后即可提交"
   : selfCheckRecovering && canSubmit ? "正在恢复自查状态…"
   : submitting ? "正在提交…"
   : ["SUBMITTED", "IN_REVIEW"].includes(submissionStatus ?? "") ? "已提交，等待审核"
   : submissionStatus === "NEEDS_REVISION" ? "待修改，请点击重新修改"
   : submissionStatus === "COMPLETED" ? "审核已通过"
   : "提交任务证据";
 const submitted = Boolean(experience?.pendingReviewAssignmentId);
 const executing = Boolean(experience);
 const taskIndex = Math.max(0, (experience?.stagePosition ?? 1) - 1);
 const [savedMaterials, setSavedMaterials] = useState<Record<string, boolean>>({});
 const savingMaterials = useRef(new Set<string>());
 const completionKey = (key: string) => `${experience?.assignmentId}:${experience?.taskVersion}:${key}`;
 const materialCompleted = (item: { key: string; completed: boolean }) => item.completed || Boolean(savedMaterials[completionKey(item.key)]);
 const openedMaterials: Record<string, boolean> = Object.fromEntries(experience?.materials.map((item, index) => [`${executionTasks[taskIndex]?.id}-material-${index + 1}`, materialCompleted(item)]) ?? []);
 const task = executionTasks[taskIndex];
 const updateExecutionRecord = (value: string) => {
   updateRecord(value);
   setChecked(false);
 };
 useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 3000); return () => window.clearTimeout(timer); }, [notice]);
 useEffect(() => {
   if (screen === "login") return;
   const code = window.sessionStorage.getItem("journey_completion_code");
   if (!code) return;
   window.sessionStorage.removeItem("journey_completion_code");
   void migrateCompletionCode(code).then(result => {
     setNotice(result.error ?? result.message ?? "历史记录迁移完成");
     if (result.ok) router.refresh();
   });
 }, [screen, router]);
 useEffect(() => {
   if (screen !== "dashboard") return;
   const refresh = () => { if (document.visibilityState === "visible") router.refresh(); };
   window.addEventListener("focus", refresh);
   document.addEventListener("visibilitychange", refresh);
   return () => { window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
 }, [screen, router]);
 const navigate = (target: Screen) => {
   if (["village","academy","guild"].includes(target)) {setScreen(target);setNotice("");return;}
   const url = new URL(window.location.href);
   if (target === "dashboard" || target === "tasks" || target === "welcome") {
     url.pathname = "/app";
     if (target === "welcome") url.searchParams.delete("view");
     else url.searchParams.set("view", target);
   } else if (target === "detail" || target === "view") {
     if (target === "view") url.searchParams.set("view", "evidence");
     else url.searchParams.delete("view");
   }
   window.history.replaceState(window.history.state, "", url);
   setScreen(target);
   setNotice("");
 };
 const assignmentForm = (kind: "draft" | "submit") => {
   if (!experience) return null;
   const data = new FormData();
   data.set("assignment_id", experience.assignmentId);
   data.set("revision", String(experience.revision));
   data.set(kind === "draft" ? "draft_idempotency_key" : "submission_idempotency_key", crypto.randomUUID());
   data.set("body", record);
   data.set("evidence_url", "");
   data.set("evidence_url_required", "false");
   data.set("submission_command", experience.allowedCommands.find(command => command.startsWith("submit")) ?? "submit");
   data.set("submission_response", "inline");
   return data;
 };
 const click = async (event: MouseEvent<HTMLElement>) => {
 const button = (event.target as HTMLElement).closest<HTMLElement>("[data-action]"); if (!button) return;
 setBurst({ x: event.clientX, y: event.clientY, key: Date.now() });
 const text = button.textContent || "";
 const action = button.dataset.action;
 if (action === "dashboard") { navigate("dashboard"); return; }
 if (action === "task-list") { navigate("tasks"); return; }
 if (action === "unavailable") { setNotice("暂未开放"); return; }
 if (action === "logout") {
   if (window.confirm("确认退出当前账号？")) await logoutSession({});
   return;
 }
 if(button.dataset.nodeId === "4062:500") { navigate("academy"); return; }
 if(button.dataset.nodeId === "4062:509") { navigate("guild"); return; }
 if (action === "review-feedback") {
   setFeedbackAssignmentId(button.dataset.assignmentId ?? null);
   return;
 }
 if (["novice-village", "ai-academy", "delivery-guild", "team-progress", "knowledge-base"].includes(action ?? "")) {
   if(action === "novice-village") navigate("village");
   else if(action === "ai-academy") navigate("academy");
   else if(action === "delivery-guild") navigate("guild");
   else setNotice("暂未开放");
   return;
 }
 if (action === "open-task") {
   const index = Number(button.dataset.taskIndex);
   if (!Number.isInteger(index) || index < 0 || index >= executionTasks.length) return;
   if (taskStatus(index) === "locked") { setNotice("需要提交上一任务"); return; }
   const assignmentId = experience?.journeyTasks.find(item => item.position === index + 1)?.assignmentId
     ?? (index === 0 && experience?.journeyTasks.length === 0 ? experience.assignmentId : undefined);
   if (assignmentId) window.location.assign(`/app/tasks/${encodeURIComponent(assignmentId)}`);
   return;
 }
 if (action === "view-task") {
   if (!experience) return;
   if (experience.materials.some(material => !materialCompleted(material))) { setNotice("请先完成学习材料"); return; }
   if (experience.allowedCommands.includes("start")) {
     const data = new FormData();
     data.set("assignment_id", experience.assignmentId);
     data.set("revision", String(experience.revision));
     data.set("destination", "evidence");
     await startAssignment(data);
   } else navigate("view");
   return;
 }
 if (action === "revise-proof" || action === "cancel-revision") {
   const command = action === "revise-proof" ? "start_evidence_revision" : "cancel_evidence_revision";
   if (!experience?.allowedCommands.includes(command) || revisionInFlight.current || submissionInFlight.current || selfCheckInFlight.current) return;
   if (action === "cancel-revision" && !window.confirm("取消本次修改？未提交的修改将被放弃，任务恢复到修改前的审核结果，历史提交会保留。")) return;
   revisionInFlight.current = true;
   setRevisionBusy(true);
   const data = new FormData();
   data.set("assignment_id", experience.assignmentId);
   data.set("revision", String(experience.revision));
   data.set("response_mode", "inline");
   try {
     if (action === "revise-proof") await startEvidenceRevision(data);
     else await cancelEvidenceRevision(data);
     window.location.assign(`/app/tasks/${experience.assignmentId}?view=evidence`);
   } catch {
     setNotice("操作未完成，请刷新页面核对任务状态后重试。");
     revisionInFlight.current = false;
     setRevisionBusy(false);
   }
   return;
 }
 if (action === "review-proof") {
   if (submissionInFlight.current || selfCheckInFlight.current || revisionInFlight.current || !canSubmit) return;
   if (effectiveCharacterCount(record) < 40 || effectiveCharacterCount(record) > 8000) { setNotice("请填写 40–8000 个有效字符的学习记录或答案链接"); return; }
   if (taskStatus(taskIndex) === "locked") { setNotice("需要提交上一任务"); return; }
   const data = assignmentForm("submit");
   if (!data) return;
   submissionInFlight.current = true;
   setSubmitting(true);
   try {
     const result = await submitAssignment({}, data);
     if (result.error) setNotice(result.error);
     else if (result.success && result.assignmentStatus) {
       window.location.assign("/app?view=tasks");
     } else setNotice("暂未取得提交结果，请刷新页面核对提交记录后再操作。");
   } catch {
     setNotice("暂未确认提交结果，请检查网络并刷新页面核对提交记录，避免重复提交。");
   } finally {
     submissionInFlight.current = false;
     setSubmitting(false);
   }
   return;
 }
 if (action === "task-link") {
   const url = task?.taskLink;
   if (url) window.open(url, "_blank", "noopener,noreferrer");
   else setNotice("当前任务暂无题目链接");
   return;
 }
 if (action === "mentor-profile") { setNotice("李魔王老师 · 产品设计导师"); return; }
 if (action === "material-1" || action === "material-2") {
   const index = action === "material-1" ? 0 : 1;
   const material = experience?.materials[index];
   const targetUrl = material?.url;
   if (!material || !targetUrl || new URL(targetUrl).hostname === "example.feishu.cn") {
     setNotice("当前材料尚未配置真实内容，请联系管理员补充材料链接。"); return;
   }
   window.open(targetUrl, "_blank", "noopener,noreferrer");
   const key = completionKey(material.key);
   if (!materialCompleted(material) && experience && !savingMaterials.current.has(key)) {
     savingMaterials.current.add(key);
     const data = new FormData();
     data.set("assignment_id", experience.assignmentId);
     data.set("material_key", material.key);
     data.set("task_version", String(experience.taskVersion));
     data.set("idempotency_key", crypto.randomUUID());
     try {
       const result = await recordOpenedLearningMaterial(data);
       if (result.error) setNotice(`材料已打开，但完成状态未保存：${result.error}`);
       else {
         setSavedMaterials(previous => ({ ...previous, [key]: true }));
         router.refresh();
       }
     } catch {
       setNotice("材料已打开，但完成状态保存失败，请重新点击材料重试。");
     } finally {
       savingMaterials.current.delete(key);
     }
   }
   return;
 }
 if (action === "execution-check") {
   if (!experience || selfCheckInFlight.current || submissionInFlight.current || revisionInFlight.current) return;
   if (!record.trim() || record.length > 2000) { setNotice("请输入一个有效飞书文档链接。"); return; }
   beginSelfCheck();
   setNotice("正在读取飞书文档并进行 AI 自查，请稍候…");
   try {
     const result = await runAiSelfCheck(experience.assignmentId, record.trim(), canSubmit ? experience.revision : undefined, crypto.randomUUID());
     setHistoryError(result.error ?? "");
     setHistoryRecords(result.records ?? []);
     if (result.record) {
       setChecked(result.record.status === "COMPLETED");
     }
     setHistoryOpen(true);
   } catch {
     setHistoryError("暂未确认自查结果，请查看历史记录，避免重复操作。");
     setHistoryOpen(true);
   } finally {
     finishSelfCheck();
     setNotice("");
   }
   return;
 }
 if (action === "execution-history") {
   if (!experience) return;
   setHistoryRecords([]);
   setHistoryError("");
   try {
     const response = await fetch(`/api/learner/tasks/${experience.assignmentId}/self-checks`, { cache: "no-store" });
     const result = await response.json() as { records?: AISelfCheckRecord[]; error?: string };
     setHistoryRecords(result.records ?? []);
     setHistoryError(result.error ?? "");
   } catch {
     setHistoryError("历史记录读取失败，请检查网络后重试。");
   }
   button.focus();
   setHistoryOpen(true);
   return;
 }
 if (text.includes("返回登录")) window.location.assign("/join");
 else if (text.includes("返回主页面")) window.location.assign("/app?view=dashboard");
 else if (text.includes("返回任务列表")) window.location.assign("/app?view=tasks");
 else if (text.includes("开启旅程")) navigate("dashboard");
 else if (text.includes("开始执行") || text.includes("继续当前")) {
   const current = experience?.journeyTasks.find(item => item.assignmentId === experience.currentAssignmentId);
   const assignmentId = current?.assignmentId ?? (experience?.journeyTasks.length === 0 ? experience.assignmentId : undefined);
   if (assignmentId) window.location.assign(`/app/tasks/${encodeURIComponent(assignmentId)}`);
   else setNotice("当前没有可执行的任务");
 }
 else if (text.includes("点击提交")) navigate("view");
 else if (text.includes("打开材料")) setNotice("设计稿未提供材料正文，请接入实际材料链接后阅读。");
 else if (text.includes("保存草稿")) { const data = assignmentForm("draft"); if (data) { const result = await saveSubmissionDraft({}, data); setNotice(result.error ?? "草稿已保存"); } }
 else if (text.includes("开始 AI 自查")) setNotice("请登录后在自己的任务中使用 AI 自查。");
 else if (["方向很多", "有判断", "遇到不确定", "知道很多"].some(word => text.includes(word))) {
   const value = button.dataset.nodeId || "";
   setChoice(value);
 }
 else if (text.includes("未解锁")) setNotice("需要先提交上一任务");
 else if (text.includes("回看任务") || text.includes("进入任务")) window.location.assign("/app?view=tasks");
 else if (text.includes("探索营")) navigate("dashboard");
 else if (text.includes("我的任务")) navigate("tasks");
 else if (text.includes("切换身份")) window.location.assign("/join");
 else setNotice("该功能尚未提供对应设计稿");
 };
 const revealLogin = useCallback(() => setEntryResourcesReady(true), []);
 if (screen === "login" && !entryResourcesReady) return <ProjectResourceLoader onReady={revealLogin} />;
 if (screen === "login") return <Login key={`${joinPhase}:${joinError}`} />;
 if (["dashboard", "village", "academy", "guild"].includes(screen)) return <ModuleHub
   module={screen as "dashboard" | "village" | "academy" | "guild"} identity={learnerName}
   nicknameRequired={joinPhase === "nickname"}
   onNavigate={navigate}
   onLogout={() => { if (window.confirm("确认退出当前账号？")) void logoutSession({}).then(result => { if (result.error) setNotice(result.error); else window.location.assign("/join"); }); }}
   decoration={<GradientStroke variant="task" strokeWidth={1} />}
   activeNavigationDecoration={<GradientStroke variant="active" strokeWidth={1.101} />}
   idleNavigationDecoration={<GradientStroke variant="idle" strokeWidth={1.101} />}
   explorationTaskCount={executionTasks.filter((_,index)=>["active", "revision"].includes(taskStatus(index))).length}
   onExplorationMenu={menu=>{ if(menu==="hall")navigate("dashboard"); else if(menu==="tasks")navigate("tasks");else setNotice("暂未开放"); }}
   dashboardContent={<><div onClick={click} onPointerMove={event=>{energizePanels(event.currentTarget,event.clientX,event.clientY);if(event.pointerType==="mouse")magnetizeControl(event.currentTarget,event.target,event.clientX,event.clientY);}} onPointerLeave={event=>resetControlMagnet(event.currentTarget)}>
     <UpdatedDashboard identity={identity} decoration={<GradientStroke variant="task" strokeWidth={1} />} activeNavigationDecoration={<GradientStroke variant="active" strokeWidth={1.101} />} idleNavigationDecoration={<GradientStroke variant="idle" strokeWidth={1.101} />} />
   </div>{selectedFeedback && <TaskFeedbackDialog feedback={selectedFeedback} title={executionTasks[selectedFeedback.position-1]?.title ?? selectedFeedback.title} onClose={()=>setFeedbackAssignmentId(null)} />}
   {burst && <ClickBurst key={burst.key} x={burst.x} y={burst.y} onFinish={()=>setBurst(null)} />}{notice && <div className="module-toast" role="status">{notice}</div>}</>}
 />;
 return <main ref={viewportRef} className="design-viewport relative min-h-dvh overflow-hidden bg-[#02091c]" data-screen={screen} onClick={click} onPointerMove={event => {
   energizePanels(event.currentTarget, event.clientX, event.clientY);
   if (screen === "dashboard" && event.pointerType === "mouse") magnetizeControl(event.currentTarget, event.target, event.clientX, event.clientY);
 }} onPointerLeave={event => {
   event.currentTarget.querySelectorAll(".holo-panel").forEach(panel => panel.removeAttribute("data-energized"));
   resetControlMagnet(event.currentTarget);
 }}>
 <div className="design-stage origin-top-left" key={screen} style={{ zoom: scale }} data-selection={choice}>
 {screen === "welcome" && <Welcome />}
 {screen === "tasks" && <Tasks />}
 {screen === "detail" && (executing ? <ExecutionDetail task={task} openedMaterials={[Boolean(openedMaterials[`${task.id}-material-1`]), Boolean(openedMaterials[`${task.id}-material-2`])]} panelDecoration={<><GradientStroke variant="panel" /><PanelFX /></>} backDecoration={<GradientStroke variant="back" />} /> : <Detail />)}
 {screen === "view" && <ExecutionView selfCheckRecovering={selfCheckRecovering} selfCheckBusy={selfCheckBusy} task={task} record={record} setRecord={updateExecutionRecord} readOnly={!canSubmit} revisionBusy={revisionBusy} canRevise={!submitting && experience?.allowedCommands.includes("start_evidence_revision")} canCancelRevision={!submitting && experience?.allowedCommands.includes("cancel_evidence_revision")} submitting={submitting} submitDisabled={selfCheckRecovering || selfCheckBusy || submitting || revisionBusy || !canSubmit} submitLabel={submitLabel} panelDecoration={<><GradientStroke variant="panel" /><PanelFX /></>} backDecoration={<GradientStroke variant="back" />} />}
 </div>
 {historyOpen && task && <SelfCheckHistory task={task} records={historyRecords} error={historyError} onClose={() => setHistoryOpen(false)} />}
 {selectedFeedback && <TaskFeedbackDialog feedback={selectedFeedback} title={executionTasks[selectedFeedback.position - 1]?.title ?? selectedFeedback.title} onClose={() => setFeedbackAssignmentId(null)} />}
 {burst && <ClickBurst key={burst.key} x={burst.x} y={burst.y} onFinish={() => setBurst(null)} />}
 {(notice || ((screen === "view" || screen === "detail") && workspaceMessage)) && <div role="status" className="fixed bottom-6 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 rounded-xl border border-cyan-300 bg-[#041a35]/95 px-6 py-3 text-center text-sm text-cyan-100 shadow-lg">{notice || workspaceMessage}</div>}
 </main>;
}

const assetPathPrefix = '/assets/project29'
const logo = `${assetPathPrefix}/6f233.webp`
const mission = `${assetPathPrefix}/c21d5.webp`
const exploreFrame = `${assetPathPrefix}/baa53.webp`
const loginArrow = `${assetPathPrefix}/79892.svg`

export function Login() {
  const { joinPhase, joinError } = useJourney();
  const [scale, setScale] = useState<number | null>(null)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [loginMode, setLoginMode] = useState<'feishu' | 'password'>('password')
  const [phoneMode, setPhoneMode] = useState<'login' | 'register' | 'reset'>('login')
  const [passwordPhone, setPasswordPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [smsCode, setSmsCode] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const [smsCountdown, setSmsCountdown] = useState(0)
  const phoneRequestInFlight = useRef(false)
  const [graduationCode, setGraduationCode] = useState('')
  const graduationCodeRef = useRef('')
  const [message, setMessage] = useState(joinError)
  const [isLaunched, setIsLaunched] = useState(false)
  const [countdown, setCountdown] = useState(10)
  const launchStarted = useRef(false)
  useEffect(() => {
    if (smsCountdown <= 0) return;
    const timer = window.setTimeout(() => setSmsCountdown(value => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [smsCountdown]);
  const switchPhoneMode = (mode: 'login' | 'register' | 'reset') => {
    if (phoneRequestInFlight.current) return;
    setPhoneMode(mode);
    setPassword('');
    setConfirmPassword('');
    setSmsCode('');
    setShowPassword(false);
    setShowConfirmPassword(false);
    setMessage('');
  };
  const sendCode = async () => {
    if (phoneRequestInFlight.current || smsCountdown > 0 || phoneMode === 'login') return;
    if (!/^1[3-9]\d{9}$/.test(passwordPhone)) { setMessage('请输入正确的手机号'); return; }
    phoneRequestInFlight.current = true;
    setSendingCode(true);
    try {
      const result = await requestPhoneCode(passwordPhone, phoneMode);
      setMessage(result.error ?? result.message ?? '');
      if (result.ok) setSmsCountdown(result.retryAfterSeconds ?? 60);
    } catch {
      setMessage('暂未确认短信发送结果，请稍后再试。');
    } finally {
      phoneRequestInFlight.current = false;
      setSendingCode(false);
    }
  };
  useEffect(() => {
    if (joinPhase !== 'feishu' || loginMode !== 'feishu' || joinError || !isFeishuClient(navigator.userAgent)) return;
    let active = true;
    const startedAt = Date.now();
    const updateCountdown = () => {
      const remaining = Math.max(0, Math.ceil((10000 - (Date.now() - startedAt)) / 1000));
      setCountdown(remaining);
      if (!launchStarted.current) setMessage(`${remaining} 秒后将使用当前飞书账号自动进入…`);
    };
    updateCountdown();
    const interval = window.setInterval(updateCountdown, 250);
    const timer = window.setTimeout(() => {
      window.clearInterval(interval);
      if (launchStarted.current) return;
      launchStarted.current = true;
      setIsLaunched(true);
      setMessage('正在使用当前飞书账号登录…');
      if (graduationCodeRef.current) window.sessionStorage.setItem('journey_completion_code', graduationCodeRef.current);
      void loginInsideFeishu().catch(error => {
        if (!active) return;
        launchStarted.current = false;
        setIsLaunched(false);
        setMessage(clientLoginErrorMessage(error));
      });
    }, 10000);
    return () => { active = false; window.clearTimeout(timer); window.clearInterval(interval); };
  }, [joinPhase, joinError, loginMode]);
  useLayoutEffect(() => {
    const resize = () => setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080))
    window.addEventListener('resize', resize)
    resize()
    return () => window.removeEventListener('resize', resize)
  }, [])

  const launch = async (event: FormEvent) => {
    event.preventDefault()
    if (joinPhase === 'feishu' && loginMode === 'feishu') {
      if (isLaunched || launchStarted.current) return;
      launchStarted.current = true;
      setIsLaunched(true);
      if (graduationCode.trim()) window.sessionStorage.setItem('journey_completion_code', graduationCode.trim().toUpperCase());
      if (isFeishuClient(navigator.userAgent)) {
        setMessage('正在获取飞书授权…');
        try {
          await loginInsideFeishu();
        } catch (error) {
          launchStarted.current = false;
          setIsLaunched(false);
          setMessage(clientLoginErrorMessage(error));
        }
        return;
      }
      setMessage('正在前往飞书授权…');
      window.location.assign('/auth/feishu?return_to=%2Fapp');
      return;
    }
    if (joinPhase === 'feishu' && loginMode === 'password') {
      if (phoneRequestInFlight.current) return;
      if (!/^1[3-9]\d{9}$/.test(passwordPhone)) { setMessage('请输入正确的手机号'); return; }
      if (password.length < 6 || password.length > 11 || /\s/.test(password)) { setMessage('密码需为 6–11 个字符，且不能包含空格'); return; }
      if (phoneMode !== 'login' && !/^\d{6}$/.test(smsCode)) { setMessage('请输入收到的 6 位短信验证码'); return; }
      if (phoneMode !== 'login' && password !== confirmPassword) { setMessage('两次输入的密码不一致，请重新确认'); return; }
      phoneRequestInFlight.current = true;
      setIsLaunched(true);
      setMessage(phoneMode === 'reset' ? '正在重置密码…' : phoneMode === 'register' ? '正在验证并注册…' : '正在验证你的探索身份…');
      try {
        if (phoneMode === 'reset') {
          const result = await resetPhonePassword(passwordPhone, smsCode, password);
          if (result.ok) {
            setPhoneMode('login');
            setPassword('');
            setConfirmPassword('');
            setSmsCode('');
            setShowPassword(false);
            setShowConfirmPassword(false);
          }
          setMessage(result.error ?? result.message ?? '');
        } else {
          const result = phoneMode === 'register'
            ? await registerWithPassword(passwordPhone, smsCode, password)
            : await loginWithPassword(passwordPhone, password);
          if (result?.error) setMessage(result.error);
        }
      } finally {
        phoneRequestInFlight.current = false;
        setIsLaunched(false);
      }
      return;
    }
    if (joinPhase === 'invite' && !code.trim()) {
      setMessage('请输入邀请码，解锁你的探索航线')
      return
    }
    if (isLaunched) return;
    setIsLaunched(true)
    setMessage('航线已校准，正在进入探索营…')
    const data = new FormData();
    if (joinPhase === 'invite') { data.set('token', code.trim()); await exchangeInvite(data); }
    else { data.set('display_name', name.trim()); data.set('accepted_purpose', 'yes'); await confirmIdentity(data); }
  }

  const magneticMove = (event: MouseEvent<HTMLButtonElement>) => {
    const button = event.currentTarget
    const rect = button.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width - 0.5
    const y = (event.clientY - rect.top) / rect.height - 0.5
    button.style.setProperty('--mx', `${x * 12}px`)
    button.style.setProperty('--my', `${y * 9}px`)
  }

  const resetMagnet = (event: MouseEvent<HTMLButtonElement>) => {
    event.currentTarget.style.setProperty('--mx', '0px')
    event.currentTarget.style.setProperty('--my', '0px')
  }

  return (
    <div className="login-viewport">
      <div className="login-canvas" style={{ zoom: scale ?? 1 }}>
      <main className={`cosmos-shell login-stage ${isLaunched ? 'is-launched' : ''}`}>
      <div className="cosmos-background" aria-hidden="true" />
      <div className="atmosphere atmosphere-one" aria-hidden="true" />
      <div className="atmosphere atmosphere-two" aria-hidden="true" />
      <div className="starfield" aria-hidden="true" />

      <header className="topbar">
        <button className="brand-mark" onClick={() => setMessage('欢迎回到沐晨新手村')} aria-label="返回首页">
          <img src={logo} alt="" />
          <span>
            <strong>MUCHEN JOURNEY</strong>
            <small>以成长·速接更大的你<br />A BIGGER YOU A BRIGHTER TOMORROW</small>
          </span>
        </button>
        <nav className="navigation" aria-label="页面工具">
          <button className="nav-control" onClick={() => setMessage(joinPhase === 'feishu' ? '点击使用飞书登录，授权后即可开始探索。' : '帮助星图已展开：输入邀请码即可开始探索。')}>
            <span className="orbit-dot">◉</span>帮助中心
          </button>
        </nav>
      </header>

      <section className="experience-grid">
        <div className="mission-zone">
          <h1 className="login-mission-title">
            <span>MUCHEN </span><span>JOURNEY</span>
            <span className="login-title-light" aria-hidden="true"><span>MUCHEN </span><span>JOURNEY</span></span>
          </h1>
          <div className="mission-art-crop">
            <img className="mission-art" src={mission} alt="沐晨新手村 AI 数据公司真实世界闯关计划" />
          </div>
          <button className="explore-button" onClick={() => setMessage('探索营信号已接收，准备开启新的任务。')}>
            <img src={exploreFrame} alt="" />
            <span>探索营</span>
          </button>
        </div>

        <form className={`login-panel login-gradient-border ${loginMode === 'feishu' ? 'login-method-panel' : ''} ${joinPhase === 'feishu' && loginMode === 'password' ? 'password-login-mode phone-account-panel' : ''}`} onSubmit={launch}>
          <GradientStroke variant="back" strokeWidth={1} animated={false} />
          <div className="panel-glow" aria-hidden="true" />
          <img className="panel-logo" src={logo} alt="" />
          <p className="panel-title">MUCHEN JOURNEY</p>
          {joinPhase === 'feishu' && <div className="login-method-tabs" role="tablist" aria-label="登录方式">
            <button disabled={isLaunched || sendingCode} type="button" role="tab" aria-selected={loginMode === 'feishu'} className={loginMode === 'feishu' ? 'active' : ''} onClick={() => { setLoginMode('feishu'); setMessage(''); }}><img src={`${assetPathPrefix}/${loginMode === 'feishu' ? '06dc8' : '7c344'}.svg`} alt="" />飞书登录</button>
            <button disabled={isLaunched || sendingCode} type="button" role="tab" aria-selected={loginMode === 'password'} className={loginMode === 'password' ? 'active' : ''} onClick={() => { setLoginMode('password'); setMessage(''); }}><img src={`${assetPathPrefix}/${loginMode === 'password' ? '3088c' : '973c8'}.svg`} alt="" />手机号登录</button>
          </div>}
          {joinPhase === 'feishu' && loginMode === 'feishu' ? <div className="login-method-fields feishu"><label className={`code-field graduation-code ${graduationCode ? 'filled' : ''}`}>
              <span className="sr-only">探索营毕业码（选填）</span>
              <input value={graduationCode} onChange={(event) => { const value = event.target.value.toUpperCase().slice(0, 20); graduationCodeRef.current = value; setGraduationCode(value); }} placeholder="探索营毕业码（选填）" autoComplete="off" />
            </label></div> : joinPhase === 'feishu' ? <div className="password-login-fields">
            {phoneMode !== 'login' && <div className="phone-account-heading">
              <h2>{phoneMode === 'register' ? '注册账号' : '重置密码'}</h2>
              <p>{phoneMode === 'register' ? '验证手机号，开启你的成长旅程' : '验证本人手机号，学习记录完整保留'}</p>
            </div>}
            <label className={`password-input-row ${passwordPhone ? 'filled' : ''}`}>
              <span className="phone-prefix">+86</span>
              <input aria-label="手机号" disabled={isLaunched || sendingCode} value={passwordPhone} onChange={(event) => { setPasswordPhone(event.target.value.replace(/\D/g, '').slice(0, 11)); setSmsCode(''); }} placeholder="请输入手机号" inputMode="tel" autoComplete="tel" maxLength={11} />
            </label>
            {phoneMode !== 'login' && <div className="otp-row">
              <label className="password-input-row">
                <input aria-label="短信验证码" disabled={isLaunched} value={smsCode} onChange={event => setSmsCode(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="6 位短信验证码" inputMode="numeric" autoComplete="one-time-code" maxLength={6} />
              </label>
              <button className="otp-button" type="button" disabled={isLaunched || sendingCode || smsCountdown > 0} onClick={sendCode}>{sendingCode ? '正在发送…' : smsCountdown > 0 ? `${smsCountdown} 秒后重发` : '获取验证码'}</button>
            </div>}
            <label className={`password-input-row ${password ? 'filled' : ''}`}>
              <input aria-label={phoneMode === 'login' ? '密码' : phoneMode === 'register' ? '设置密码' : '设置新密码'} disabled={isLaunched} value={password} onChange={(event) => setPassword(event.target.value.slice(0, 11))} placeholder={phoneMode === 'login' ? '请输入密码（6–11位）' : phoneMode === 'register' ? '设置密码（6–11位）' : '设置新密码（6–11位）'} type={showPassword ? 'text' : 'password'} autoComplete={phoneMode === 'login' ? 'current-password' : 'new-password'} maxLength={11} />
              <button type="button" className="password-visibility" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? '隐藏' : '显示'}</button>
            </label>
            {phoneMode !== 'login' && <label className="password-input-row">
              <input aria-label={phoneMode === 'register' ? '确认密码' : '确认新密码'} disabled={isLaunched} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value.slice(0, 11))} placeholder={phoneMode === 'register' ? '请再次输入密码' : '请再次输入新密码'} type={showConfirmPassword ? 'text' : 'password'} autoComplete="new-password" maxLength={11} />
              <button type="button" className="password-visibility" aria-label={showConfirmPassword ? '隐藏确认密码' : '显示确认密码'} aria-pressed={showConfirmPassword} onClick={() => setShowConfirmPassword(value => !value)}>{showConfirmPassword ? '隐藏' : '显示'}</button>
            </label>}
            <div className="password-login-guidance">
              {phoneMode === 'login' ? <>
                <button disabled={isLaunched || sendingCode} type="button" className="forgot-password-button" onClick={() => switchPhoneMode('register')}>注册账号</button>
                <span aria-hidden="true">|</span>
                <button disabled={isLaunched || sendingCode} type="button" className="forgot-password-button" onClick={() => switchPhoneMode('reset')}>忘记密码？</button>
              </> : <button disabled={isLaunched || sendingCode} type="button" className="forgot-password-button" onClick={() => switchPhoneMode('login')}>← 返回登录</button>}
            </div>
            <p className="phone-login-note">{phoneMode === 'register' ? '注册' : phoneMode === 'reset' ? '继续' : '登录'}即代表您已阅读并同意
              <a href="https://zx6w57w0j34.feishu.cn/docx/Oxexd1UMdoHg2YxEOYVcx5fonkd" target="_blank" rel="noreferrer">《用户服务协议》</a>
              与
              <a href="https://zx6w57w0j34.feishu.cn/docx/Oxexd1UMdoHg2YxEOYVcx5fonkd" target="_blank" rel="noreferrer">《隐私政策》</a>
            </p>
          </div> : <label className={`code-field ${(joinPhase === 'invite' ? code : name) ? 'filled' : ''}`}>
            <span className="sr-only">{joinPhase === 'invite' ? '邀请码' : '昵称'}</span>
            {joinPhase === 'invite' ? <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="请输入邀请码" autoComplete="one-time-code" /> : <input value={name} onChange={(event) => setName(event.target.value)} placeholder="请输入昵称" autoComplete="nickname" />}
          </label>}
          {joinPhase === 'feishu' && loginMode === 'feishu' && <div className="login-agreement" />}
          <button disabled={isLaunched || sendingCode} className="launch-button" type="submit" onMouseMove={magneticMove} onMouseLeave={resetMagnet}>
            <img src={loginArrow} alt="" />
            <span>{isLaunched ? '正在处理…' : joinPhase === 'feishu' ? loginMode === 'password' ? phoneMode === 'register' ? '注册并登录' : phoneMode === 'reset' ? '重置密码' : '登录并开始探索' : '登录并开始探索' : joinPhase === 'invite' ? '解锁探索航线' : '进入探索营'}</span>
            <b aria-hidden="true" />
          </button>
          <div className="status-line" role="status">{message}</div>
          {joinPhase === 'feishu' && loginMode === 'feishu' && !joinError && !isLaunched && isFeishuClient(typeof navigator === 'undefined' ? '' : navigator.userAgent) && <span className="login-auto-countdown" aria-hidden="true">{countdown}</span>}
        </form>
      </section>

      <footer><span>AI 驱动成长 - 连接真实世界</span><span>——————探索·实践·成长·创造更大的价值</span></footer>
      </main>
      </div>
    </div>
  )
}

function Tasks() {
const taskStatus = useTaskStatus();
const {learnerName} = useJourney();
const completed = executionTasks.filter((_, index) => taskStatus(index) === "completed").length;
const current = executionTasks.find((_, index) => taskStatus(index) === "revision") ?? executionTasks.find((_, index) => taskStatus(index) === "active");
const assetPathPrefix = "/assets/project29";
const imgImage74 = `${assetPathPrefix}/90975.webp`;
const imgRectangle60 = `${assetPathPrefix}/59316.svg`;


  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-node-id="2006:305" data-name="任务列表">
      <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:306">
        <div className="col-1 h-[1080px] ml-0 mt-0 relative row-1 w-[1920px]" data-node-id="2006:307" data-name="image 74">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage74} />
        </div>
        <div className="col-1 h-[28.984px] ml-[107px] mt-[346px] relative row-1 w-[425px]" data-node-id="2006:308" data-name="Container">
          <div className="absolute bg-[#1a4669] h-[28.172px] left-0 top-[-15.19px] w-[197.563px]" data-node-id="2006:309" data-name="Text">
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[19.8px] left-[11.39px] not-italic text-[#8defff] text-[12px] top-[3.19px] tracking-[1.44px] whitespace-nowrap" data-node-id="2006:310">
              你好，{learnerName} · 你的成长航线
            </p>
          </div>
        </div>
        <div className="col-1 content-stretch flex flex-col items-center justify-center max-w-[515.375px] ml-[107px] mt-[374.98px] relative row-1" data-node-id="2006:311" data-name="Heading 1">
          <div className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[0] not-italic relative shrink-0 text-[#f2fcff] text-[56px] tracking-[3.36px] whitespace-nowrap font-bold" data-node-id="2006:312">
            <p className="leading-[60.48px] mb-0 text-[#3ed8ef]">下一站</p>
            <p className="leading-[60.48px]">{current?.label || "旅程完成"}</p>
          </div>
        </div>
        <div className="col-1 content-stretch flex flex-col items-start max-w-[660px] ml-[107px] mt-[495.98px] pb-[16px] pt-[14px] relative row-1 w-[425px]" data-node-id="2006:313" data-name="Paragraph">
          <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[28.8px] not-italic relative shrink-0 text-[#9bbad3] text-[16px] w-full" data-node-id="2006:314">
            完成材料并提交真实任务证据后，下一站会由系统自动解锁；你可以随时回看已经完成的旅程。
          </p>
        </div>
        <div className="col-1 h-[48.391px] ml-[107px] mt-[583.98px] relative row-1 w-[425px]" data-node-id="2006:315" data-name="Container">
          <button type="button" data-action="true" className="absolute bg-gradient-to-r border border-[#75f5ff] border-solid content-stretch flex from-[#42dced] gap-[10px] items-center justify-center left-0 min-h-[48px] px-[20px] py-[10px] rounded-[7px] shadow-[0px_0px_14px_0px_#2edfff,0px_0px_26px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[12px] via-[#31c9f5] via-[45%]" data-node-id="2006:316" data-name="Link">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[26.4px] not-italic relative shrink-0 text-[#03245f] text-[16px] tracking-[1.28px] whitespace-nowrap font-black" data-node-id="2006:317">
              继续当前任务
            </p>
            <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:318" data-name="Text">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[26.4px] not-italic relative shrink-0 text-[#03245f] text-[16px] tracking-[1.28px] whitespace-nowrap font-black" data-node-id="2006:319">
                →
              </p>
            </div>
          </button>
        </div>
        <div className="[word-break:break-word] bg-[rgba(255,255,255,0)] border-10 border-[#194a6a] border-solid col-1 ml-[107px] mt-[679px] not-italic relative rounded-[75px] row-1 shadow-[0px_0px_25px_0px_rgba(46,223,255,0.24)] size-[150px] text-center whitespace-nowrap" data-node-id="2006:320" data-name="Container">
          <p className="-translate-x-1/2 absolute font-['Source_Han_Sans_SC'] leading-[0] left-[64.99px] text-[#eafdff] text-[0px] top-[17.16px] font-bold" data-node-id="2006:321">
            <span className="leading-[75.9px] text-[46px]">{completed}</span>
            <span className="leading-[26.4px] text-[#75a6c4] text-[16px]">/08</span>
          </p>
          <p className="-translate-x-1/2 absolute font-['Source_Han_Sans_SC'] leading-[19.8px] left-[64.99px] text-[#86c9e5] text-[12px] top-[93.05px] tracking-[1.8px]" data-node-id="2006:322">
            完成进度
          </p>
        </div>
        <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 content-stretch flex flex-col items-start ml-[654px] mt-[86px] p-[24px] relative rounded-[16px] row-1 shadow-[0px_0px_39.9px_0px_rgba(0,112,191,0.66)] w-[1180px] figma-stroke figma-stroke-panel holo-panel" data-node-id="2006:323" data-name="Section"><GradientStroke variant="panel" /><PanelFX />
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px] journey-task-panel-tint" />
          <div className="border-[rgba(65,164,214,0.25)] border-b border-solid content-stretch flex items-end justify-between pb-[14px] relative shrink-0 w-full" data-node-id="2006:324" data-name="Header">
            <div className="content-stretch flex flex-col items-start relative shrink-0 w-[150px]" data-node-id="2006:325" data-name="Container">
              <div className="h-[26.391px] relative shrink-0 w-full" data-node-id="2006:326" data-name="Container">
                <p className="-translate-x-full [word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[18.15px] left-[37px] not-italic text-[#59e6f4] text-[11px] text-right top-[4px] tracking-[1.98px] whitespace-nowrap" data-node-id="2006:327">
                  探索营
                </p>
              </div>
              <div className="content-stretch flex flex-col h-[36px] items-start pt-[4px] relative shrink-0 w-full" data-node-id="2006:328" data-name="Heading 2">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[31.25px] not-italic relative shrink-0 text-[#e9f9ff] text-[25px] text-right whitespace-nowrap font-bold" data-node-id="2006:329">
                  全部成长任务
                </p>
              </div>
            </div>
          </div>
          <div className="content-stretch flex flex-col items-start pt-[22px] relative shrink-0 w-full" data-node-id="2006:332" data-name="Container:margin">
            <TaskCards />
          </div>
          <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_16px_3px_44.8px_0px_rgba(114,133,255,0.36)]" />
        </div>
        <button type="button" data-action="true" className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[114px] mt-[105px] place-items-start relative row-1" data-node-id="2006:454">
          <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2006:455">
            <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 h-[68px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[261px] figma-stroke figma-stroke-back" data-node-id="2006:456"><GradientStroke variant="back" />
              <div aria-hidden className="absolute inset-0 rounded-[16px] journey-back-tint" />
              <div className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
            </div>
          </div>
          <div className="col-1 content-stretch flex gap-[24px] items-center justify-center ml-[20px] mt-[19px] relative row-1 w-[221.245px]" data-node-id="2006:457">
            <div className="flex h-[20.956px] items-center justify-center relative shrink-0 w-[20.961px]" data-node-id="2006:458">
              <div className="-scale-y-100 flex-none rotate-[134.03deg]">
                <div className="h-[14.922px] relative w-[14.722px]">
                  <div className="absolute inset-[-6.7%_-6.79%]">
                    <img alt="" className="block max-w-none size-full" src={imgRectangle60} />
                  </div>
                </div>
              </div>
            </div>
            <div className="content-stretch flex items-center relative shrink-0" data-node-id="2006:459">
              <div className="content-stretch flex flex-col items-start relative shrink-0 w-[124px]" data-node-id="2006:460">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[21px] text-white w-full font-medium" data-node-id="2006:461">
                  返回主页面
                </p>
              </div>
            </div>
          </div>
        </button>
      </div>
    </div>
  );
}
function Detail() {
const {learnerName} = useJourney();const assetPathPrefix = "/assets/project29";
const imgImage74 = `${assetPathPrefix}/90975.webp`;
const imgRectangle60 = `${assetPathPrefix}/59316.svg`;


  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-node-id="2006:462" data-name="任务详情">
      <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:463">
        <div className="col-1 h-[1080px] ml-0 mt-0 relative row-1 w-[1920px]" data-node-id="2006:464" data-name="image 74">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage74} />
        </div>
        <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 content-stretch flex flex-col items-start ml-[654px] mt-[86px] p-[24px] relative rounded-[16px] row-1 shadow-[0px_0px_39.9px_0px_rgba(0,112,191,0.66)] w-[1180px] figma-stroke figma-stroke-panel holo-panel" data-node-id="2006:465" data-name="Section"><GradientStroke variant="panel" /><PanelFX />
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px] journey-detail-panel-tint" />
          <div className="border-[rgba(65,164,214,0.25)] border-b border-solid h-[169px] relative shrink-0 w-full" data-node-id="2006:466" data-name="Header">
            <div className="absolute content-stretch flex flex-col items-start left-0 top-0 w-[150px]" data-node-id="2006:467" data-name="Container">
              <div className="h-[26.391px] relative shrink-0 w-full" data-node-id="2006:468" data-name="Container">
                <p className="-translate-x-full [word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[31.906px] left-[65.4px] not-italic text-[#59e6f4] text-[19.337px] text-right top-[4px] tracking-[3.4806px] whitespace-nowrap" data-node-id="2006:469">
                  探索营
                </p>
              </div>
              <div className="content-stretch flex flex-col h-[36px] items-start pt-[4px] relative shrink-0 w-full" data-node-id="2006:470" data-name="Heading 2">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[82.014px] not-italic relative shrink-0 text-[#e9f9ff] text-[49.706px] text-right whitespace-nowrap font-bold" data-node-id="2006:471">
                  Day 1｜启程-公司基础介绍材料
                </p>
              </div>
            </div>
            <div className="absolute h-[22px] left-[1055.8px] top-[40.39px] w-[73px]" data-node-id="2006:472" data-name="Small" />
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[28.8px] left-[0.4px] not-italic text-[#b2c0db] text-[16px] top-[116.4px] whitespace-nowrap" data-node-id="2006:473">
              验证新人可以先完成学习输入，再留下当前阶段的结构化证据并继续旅程。
            </p>
          </div>
          <div className="h-[639.6px] relative shrink-0 w-[1095.57px]" data-node-id="2006:474" data-name="Container:margin">
            <div className="absolute h-[681.334px] left-0 right-0 top-[21.35px]" data-node-id="2006:475" data-name="Container">
              <div className="absolute gap-x-[26.432388305664062px] gap-y-[26.432388305664062px] grid-cols-[__528.65px_528.65px] grid-rows-[_372px] inline-grid left-[19.4px] top-[15.05px]" data-node-id="2006:476" data-name="Container">
                <div className="border border-[#31b7a9] border-solid col-1 content-stretch flex flex-col items-start justify-self-stretch p-[19px] relative rounded-[8px] row-1 self-stretch shrink-0" data-node-id="2006:477" style={{ backgroundImage: "linear-gradient(153.76941883082628deg, rgba(6, 65, 72, 0.74) 6.1733%, rgba(3, 38, 46, 0.84) 50%, rgba(0, 17, 26, 0.94) 93.827%)" }} data-name="Article">
                  <div className="content-stretch flex items-center justify-between relative shrink-0 w-full" data-node-id="2006:478" data-name="Header">
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:479" data-name="Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[31.152px] not-italic relative shrink-0 text-[#72a9c8] text-[18.88px] tracking-[2.2656px] whitespace-nowrap" data-node-id="2006:480">
                        材料 01
                      </p>
                    </div>
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:481" data-name="Bold Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[39.6px] not-italic relative shrink-0 text-[#77ffcf] text-[24px] text-right whitespace-nowrap font-black" data-node-id="2006:482">
                        已完成
                      </p>
                    </div>
                  </div>
                  <div className="content-stretch flex flex-col h-[117.058px] items-start min-h-[90.62533569335938px] pt-[26.432px] relative shrink-0 w-[464.455px]" data-node-id="2006:483" data-name="Heading 2">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[45.313px] not-italic relative shrink-0 text-[#eefcff] text-[30.208px] whitespace-nowrap font-bold" data-node-id="2006:484">
                      给 Muchener 的一封信
                    </p>
                  </div>
                  <div className="content-stretch flex flex-col h-[77.409px] items-start pb-[28.32px] pt-[13.216px] relative shrink-0 w-[464.455px]" data-node-id="2006:485" data-name="Paragraph">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[34.268px] not-italic relative shrink-0 text-[#799db8] text-[20.768px] whitespace-nowrap" data-node-id="2006:486">
                      了解旅程的起点与真实问题。
                    </p>
                  </div>
                  <button type="button" data-action="true" className="bg-[rgba(39,151,181,0.17)] border-[#75f5ff] border-[1.888px] border-solid content-stretch flex h-[83.811px] items-center justify-center min-h-[75.52111053466797px] px-[22.656px] py-[15.104px] relative rounded-[11.328px] shrink-0 w-[464.455px]" data-node-id="2006:487" data-name="Link">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[49.844px] not-italic relative shrink-0 text-[#dffcff] text-[30.208px] whitespace-nowrap font-black" data-node-id="2006:488">
                      重新打开材料 01
                    </p>
                  </button>
                </div>
                <div className="border border-[#48eaff] border-solid col-2 content-stretch flex flex-col items-start justify-self-stretch p-[19px] relative rounded-[8px] row-1 self-stretch shadow-[0px_0px_18px_0px_rgba(46,223,255,0.2)] shrink-0" data-node-id="2006:489" data-name="Article">
                  <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[8px]" style={{ backgroundImage: "linear-gradient(153.76941883082628deg, rgba(12, 38, 68, 0.9) 6.1733%, rgba(1, 11, 24, 0.94) 93.827%)" }} />
                  <div className="content-stretch flex items-center justify-between relative shrink-0 w-full" data-node-id="2006:490" data-name="Header">
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:491" data-name="Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[31.152px] not-italic relative shrink-0 text-[#72a9c8] text-[18.88px] tracking-[2.2656px] whitespace-nowrap" data-node-id="2006:492">
                        材料 02
                      </p>
                    </div>
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:493" data-name="Bold Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[39.6px] not-italic relative shrink-0 text-[#315b7e] text-[24px] text-right whitespace-nowrap font-black" data-node-id="2006:494">
                        进行中
                      </p>
                    </div>
                  </div>
                  <div className="content-stretch flex flex-col h-[117.058px] items-start min-h-[90.62533569335938px] pt-[26.432px] relative shrink-0 w-[464.455px]" data-node-id="2006:495" data-name="Heading 2">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[45.313px] not-italic relative shrink-0 text-[#eefcff] text-[30.208px] whitespace-nowrap font-bold" data-node-id="2006:496">
                      公司基础介绍材料
                    </p>
                  </div>
                  <div className="content-stretch flex flex-col h-[77.409px] items-start pb-[28.32px] pt-[13.216px] relative shrink-0 w-[464.455px]" data-node-id="2006:497" data-name="Paragraph">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[34.268px] not-italic relative shrink-0 text-[#799db8] text-[20.768px] whitespace-nowrap" data-node-id="2006:498">
                      建立对公司业务与工作方式的基础认知。
                    </p>
                  </div>
                  <button type="button" data-action="true" className="bg-[rgba(39,151,181,0.17)] border-[#75f5ff] border-[1.888px] border-solid content-stretch flex h-[83.811px] items-center justify-center min-h-[75.52111053466797px] px-[22.656px] py-[15.104px] relative rounded-[11.328px] shrink-0 w-[464.455px]" data-node-id="2006:499" data-name="Link">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[49.844px] not-italic relative shrink-0 text-[#dffcff] text-[30.208px] whitespace-nowrap font-black" data-node-id="2006:500">
                      打开材料 02
                    </p>
                  </button>
                  <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_0px_0px_28px_0px_rgba(35,176,241,0.13)]" />
                </div>
              </div>
              <button type="button" data-action="true" className="absolute bg-gradient-to-r border-[#75f5ff] border-[2.149px] border-solid from-[#42dced] h-[104.397px] left-[344.4px] rounded-[15.042px] shadow-[0px_0px_30.084px_0px_#2edfff,0px_0px_55.871px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[462.05px] via-[#31c9f5] via-[45%] w-[437px]" data-node-id="2006:501" data-name="Link">
                <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[56.73px] left-[42.98px] not-italic text-[#03245f] text-[34.382px] top-[21.49px] tracking-[2.7505px] whitespace-nowrap font-black" data-node-id="2006:502">
                  点击提交任务证据
                </p>
                <div className="absolute content-stretch flex flex-col items-start left-[359.43px] top-[21.49px]" data-node-id="2006:503" data-name="Text">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[56.73px] not-italic relative shrink-0 text-[#03245f] text-[34.382px] tracking-[2.7505px] whitespace-nowrap font-black" data-node-id="2006:504">
                    →
                  </p>
                </div>
              </button>
            </div>
          </div>
          <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_16px_3px_44.8px_0px_rgba(114,133,255,0.36)]" />
        </div>
        <button type="button" data-action="true" className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[114px] mt-[105px] place-items-start relative row-1" data-node-id="2006:505">
          <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2006:506">
            <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 h-[68px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[261px] figma-stroke figma-stroke-back" data-node-id="2006:507"><GradientStroke variant="back" />
              <div aria-hidden className="absolute inset-0 rounded-[16px] journey-back-tint" />
              <div className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
            </div>
          </div>
          <div className="col-1 content-stretch flex gap-[24px] items-center justify-center ml-[20px] mt-[19px] relative row-1 w-[221.245px]" data-node-id="2006:508">
            <div className="flex h-[20.956px] items-center justify-center relative shrink-0 w-[20.961px]" data-node-id="2006:509">
              <div className="-scale-y-100 flex-none rotate-[134.03deg]">
                <div className="h-[14.922px] relative w-[14.722px]">
                  <div className="absolute inset-[-6.7%_-6.79%]">
                    <img alt="" className="block max-w-none size-full" src={imgRectangle60} />
                  </div>
                </div>
              </div>
            </div>
            <div className="content-stretch flex items-center relative shrink-0" data-node-id="2006:510">
              <div className="content-stretch flex flex-col items-start relative shrink-0 w-[124px]" data-node-id="2006:511">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[21px] text-white w-[141px] font-medium" data-node-id="2006:512">
                  返回任务列表
                </p>
              </div>
            </div>
          </div>
        </button>
        <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[107px] mt-[348px] place-items-start relative row-1" data-node-id="2006:513">
          <div className="bg-[#1a4669] col-1 h-[41.999px] ml-0 mt-0 relative row-1 w-[294.529px]" data-node-id="2006:514" data-name="Text">
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[29.518px] left-[16.98px] not-italic text-[#8defff] text-[17.89px] top-[4.75px] tracking-[2.1468px] whitespace-nowrap" data-node-id="2006:515">
              你好，{learnerName} · 你的成长航线
            </p>
          </div>
          <div className="col-1 content-stretch flex flex-col items-center justify-center max-w-[515.375px] ml-0 mt-[75px] relative row-1" data-node-id="2006:516" data-name="Heading 1">
            <div className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[0] not-italic relative shrink-0 text-[#f2fcff] text-[0px] tracking-[3.36px] whitespace-nowrap font-bold" data-node-id="2006:517">
              <p className="leading-[75px] mb-0 text-[#3ed8ef] text-[68px]">DAY 1</p>
              <p className="leading-[75px] text-[68px]">启程</p>
            </div>
          </div>
          <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] leading-[28.8px] ml-0 mt-[258px] not-italic relative row-1 text-[#9bbad3] text-[20px] w-[367px]" data-node-id="2006:518">{` 建立业务范围、发展历程与经营理念的基础认知。阅读材料后，可以填写读后感或文档链接作为任务证据。`}</p>
        </div>
      </div>
    </div>
  );
}
function Welcome() {
const {learnerName}=useJourney();
return <div className="relative h-[1080px] w-[1920px] text-[#f2fcff]" data-node-id="2006:578">
<img src="/assets/project29/90975.webp" alt="" className="absolute inset-0 h-full w-full object-cover" />
<button type="button" data-action="true" data-node-id="2006:590" className="welcome-back figma-stroke figma-stroke-back absolute left-[114px] top-[105px] h-[68px] w-[261px] rounded-[16px] border-[1.6px] border-transparent">
  <div aria-hidden="true" className="absolute inset-0 rounded-[16px] bg-[linear-gradient(255.0525143236887deg,rgba(201,231,255,0.49)_2.4688%,rgba(52,113,195,0.202)_14.255%,rgba(1,14,105,0.407)_44.37%,rgba(10,0,153,0.49)_90.024%)]" />
  <div aria-hidden="true" className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
  <GradientStroke variant="back" />
  <span className="absolute left-[20px] top-[19px] flex w-[221.245px] items-center justify-center gap-[24px]">
    <span aria-hidden="true" className="relative flex h-[20.956px] w-[20.961px] shrink-0 items-center justify-center">
      <span className="-scale-y-100 rotate-[134.03deg]"><span className="relative block h-[14.922px] w-[14.722px]"><span className="absolute inset-[-6.7%_-6.79%]"><img src="/assets/project29/59316.svg" alt="" className="block max-w-none" /></span></span></span>
    </span>
    <span className="relative flex w-[124px] shrink-0 flex-col items-start"><span className="w-[141px] font-['Source_Han_Sans_SC'] text-[21px] font-medium leading-[normal] text-white">返回登录页</span></span>
  </span>
</button>
<div className="absolute left-[107px] top-[348px]">
  <p className="relative isolate flex w-max items-center gap-[12px] overflow-hidden whitespace-nowrap rounded-[12px] border border-[#71c5ff]/45 bg-[#1a4669]/85 px-[17px] py-[5px] font-['Source_Han_Sans_SC'] text-[17.89px] leading-[30px] tracking-[2.1468px] text-[#8defff] animate-[welcome-signal-breathe_4s_ease-in-out_infinite] motion-reduce:animate-none">
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[linear-gradient(110deg,transparent_35%,rgba(113,197,255,0.10)_44%,rgba(232,246,255,0.32)_50%,rgba(109,111,255,0.12)_56%,transparent_65%)] animate-[welcome-signal-sweep_4.5s_ease-in-out_infinite] motion-reduce:hidden" />
    <span aria-hidden="true" className="relative h-[7px] w-[7px] shrink-0 rounded-full bg-[#8defff] shadow-[0_0_10px_#51abff] animate-[welcome-signal-beacon_2.4s_ease-in-out_infinite] motion-reduce:animate-none" />
    <span className="relative">你好，{learnerName} · 你的成长航线</span>
  </p>
  <h1 className="mt-[33px] font-bold text-[68px] leading-[93px] tracking-[3.36px]"><span className="text-[#3ed8ef]">欢迎来到</span><br />MUCHEN<br />JOURNEY</h1>
</div>
<button type="button" data-action="true" data-node-id="2006:603" className="absolute left-[107px] top-[774px] flex h-[78px] w-[379px] items-center justify-center rounded-[12.482px] border-[1.135px] border-[#75f5ff] bg-gradient-to-r from-[#42dced] via-[#31c9f5] via-[45%] to-[#5ceeff] px-[6.809px] py-[1.135px] shadow-[0_0_18.156px_#2edfff,0_0_36.312px_rgba(18,195,255,0.55)]">
  <span className="relative flex shrink-0 items-center">
    <span aria-hidden="true" className="relative h-[27.234px] w-[23.83px] shrink-0"><img src="/assets/project29/37de3.svg" alt="" className="absolute inset-0 block max-w-none" /></span>
    <span className="relative w-[231.489px] shrink-0 text-center font-['Source_Han_Sans_SC'] text-[23.83px] font-black leading-[normal] tracking-[4.539px] text-[#03245f]">开启旅程</span>
  </span>
</button>
<section className="figma-stroke figma-stroke-panel holo-panel absolute left-[654px] top-[105px] flex h-[817px] w-[1180px] flex-col gap-[26px] rounded-[16px] border-[1.6px] border-[#e8f6ff] bg-gradient-to-l from-[#00325b]/41 via-[#000737]/34 to-[#07015e]/41 px-[56px] py-[24px] shadow-[0_0_39.9px_#0070bfa8,inset_16px_3px_44.8px_#7285ff5c]"><GradientStroke variant="panel" /><PanelFX /><header className="h-[169px] shrink-0 border-b border-[#41a4d6]/25 pt-[30px]"><h2 className="text-[68px] font-bold leading-[93px] tracking-[3.36px]">MUCHEN JOURNEY</h2></header><WelcomeNarrative /></section></div>;
}

const welcomeParagraphs = [
  "Muchen Journey是沐晨面向新人和在岗成员建设的学习与实践成长平台。平台将公司资料、岗位任务、AI 学习、实践交付和导师审核连接起来，帮助成员按照阶段完成学习与工作任务，并沉淀可回看的成果、反馈和成长记录。",
  "平台采用游戏化的成长体验，将学习内容和真实任务组织成连续的成长旅程。用户登录后可以看到当前阶段、下一项行动、任务要求、审核人和完成结果。",
];

function WelcomeNarrative() {
  const characters = Array.from(welcomeParagraphs.join(""));
  const total = characters.length;
  const [revealed, setRevealed] = useState(0);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    let position = 0;
    const revealAll = () => {
      if (!preference.matches) return;
      window.clearTimeout(timer);
      setRevealed(total);
    };
    const tick = () => {
      position += 1;
      setRevealed(position);
      if (position >= total) return;
      const delay = /[。，；、]/.test(characters[position - 1]) ? 160 : 32;
      timer = window.setTimeout(tick, delay);
    };
    if (preference.matches) timer = window.setTimeout(revealAll, 0);
    else timer = window.setTimeout(tick, 350);
    preference.addEventListener("change", revealAll);
    return () => {
      window.clearTimeout(timer);
      preference.removeEventListener("change", revealAll);
    };
  }, []);
  return <div className="text-[40px] leading-[64px] tracking-[3.36px] text-[#a3c0ff]" data-welcome-narrative="true">
    <div className="sr-only">{welcomeParagraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}</div>
    <div aria-hidden="true">{welcomeParagraphs.map((paragraph, paragraphIndex) => {
      const start = Array.from(welcomeParagraphs.slice(0, paragraphIndex).join("")).length;
      const letters = Array.from(paragraph);
      return <p key={paragraph}>{letters.map((character, index) => {
        const position = start + index;
        return <span key={position} className={position < revealed ? "relative visible" : "relative invisible"}>
          {character}
          {position === revealed - 1 && revealed < total && <span className="pointer-events-none absolute -right-[3px] top-[.15em] h-[.9em] w-[2px] animate-pulse bg-[#8defff] shadow-[0_0_8px_#51abff] motion-reduce:hidden" />}
        </span>;
      })}</p>;
    })}</div>
  </div>;
}

function GradientStroke({ variant, strokeWidth, animated = true }: { variant: "active" | "idle" | "task" | "panel" | "back"; strokeWidth?: number; animated?: boolean }) {
  const gradientId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 302, height: 108 });
  useLayoutEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const update = () => setSize({ width: svg.clientWidth, height: svg.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);
  const angle = (variant === "active" ? 111 : variant === "idle" ? 97.83 : variant === "panel" ? 45.46 : variant === "back" ? 105.82 : 57.83) * Math.PI / 180;
  const directionX = Math.sin(angle);
  const directionY = -Math.cos(angle);
  const halfLength = (Math.abs(size.width * directionX) + Math.abs(size.height * directionY)) / 2;
  const stops: [number, string, number][] = (variant === "active" || variant === "back")
    ? [[0, "#e8f6ff", 1], [13, "#71c5ff", 1], [35, "#0063a7", 1], [64, "#6857ff", 1], [96, "#789eff", 1]]
    : variant === "panel"
      ? [[0, "#e8f6ff", 1], [9, "#226089", 1], [28, "#51abff", .75], [45, "#314a88", 1], [59, "#ffffff", 1], [82, "#6d6fff", 1], [100, "#ffffff", 1]]
    : variant === "idle"
      ? [[0, "#3a3e91", 1], [13, "#092e47", 1], [35, "#342e69", 1], [64, "#3d3676", 1], [100, "#2b5378", 1]]
      : [[0, "#1e3961", .85], [26, "#529cc8", .91], [42, "#0f1f3e", .94], [53, "#87b1ff", 1], [76, "#1e4380", .91], [93, "#3e94db", .88], [100, "#67b6f2", 1]];
  const width = strokeWidth ?? (variant === "task" ? 2 : 1.6);
  return <svg ref={svgRef} className="figma-stroke-svg" aria-hidden="true" focusable="false">
    <defs><linearGradient id={gradientId} gradientUnits="userSpaceOnUse" x1={size.width / 2 - directionX * halfLength} y1={size.height / 2 - directionY * halfLength} x2={size.width / 2 + directionX * halfLength} y2={size.height / 2 + directionY * halfLength}>
      {stops.map(([offset, color, opacity]) => <stop key={offset} offset={offset + "%"} stopColor={color} stopOpacity={opacity} />)}
    </linearGradient></defs>
    <rect className="figma-stroke-rect" x={width / 2} y={width / 2} rx={variant === "task" ? 17 : 15.2} fill="none" stroke={"url(#" + gradientId + ")"} strokeWidth={width} />
    {animated && <rect className="figma-stroke-rect orbit-tracer" x={width / 2} y={width / 2} rx={variant === "task" ? 17 : 15.2} fill="none" stroke="#b8f5ff" strokeWidth={width} pathLength={1000} strokeDasharray="35 965" strokeLinecap="round" />}
    {variant === "panel" && <rect className="figma-stroke-rect orbit-tracer orbit-tracer-reverse" x={width / 2} y={width / 2} rx={15.2} fill="none" stroke="#b5aaff" strokeWidth={width} pathLength={1000} strokeDasharray="55 945" strokeLinecap="round" />}
  </svg>;
}

function ClickBurst({ x, y, onFinish }: { x: number; y: number; onFinish: () => void }) {
  return <div className="click-burst" aria-hidden="true" style={{ left: x, top: y }} onAnimationEnd={event => { if (event.target === event.currentTarget) onFinish(); }}>
    <span className="burst-ring" />
    {Array.from({ length: 14 }, (_, index) => {
      const angle = index * Math.PI * 2 / 14;
      const distance = 36 + (index % 3) * 16;
      return <span className="burst-spark" key={index} style={{ "--spark-x": Math.cos(angle) * distance + "px", "--spark-y": Math.sin(angle) * distance + "px", "--spark-delay": index % 3 * 25 + "ms" } as CSSProperties} />;
    })}
  </div>;
}

function energizePanels(root: HTMLElement, pointerX: number, pointerY: number) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  root.querySelectorAll<HTMLElement>(".holo-panel").forEach(panel => {
    const bounds = panel.getBoundingClientRect();
    const inside = pointerX >= bounds.left && pointerX <= bounds.right && pointerY >= bounds.top && pointerY <= bounds.bottom;
    if (!inside) { panel.removeAttribute("data-energized"); return; }
    panel.setAttribute("data-energized", "true");
    panel.style.setProperty("--holo-x", (pointerX - bounds.left) / bounds.width * 100 + "%");
    panel.style.setProperty("--holo-y", (pointerY - bounds.top) / bounds.height * 100 + "%");
  });
}
function PanelFX() {
  return <div className="holo-fx" aria-hidden="true">
    <div className="holo-spotlight" />
    <div className="holo-radar"><span /><span /><span /></div>
    <div className="holo-grid" />
    <div className="holo-scanline" />
    <span className="holo-corner holo-corner-tl" /><span className="holo-corner holo-corner-tr" />
    <span className="holo-corner holo-corner-bl" /><span className="holo-corner holo-corner-br" />
    <div className="holo-dust">{Array.from({ length: 8 }, (_, index) => <span key={index} />)}</div>
  </div>;
}

function resetControlMagnet(root: HTMLElement, except?: HTMLElement | null) {
  root.querySelectorAll<HTMLElement>("[data-magnetic]").forEach(control => {
    if (control === except) return;
    control.removeAttribute("data-magnetic");
    control.style.removeProperty("--control-x");
    control.style.removeProperty("--control-y");
  });
}

function magnetizeControl(root: HTMLElement, target: EventTarget, pointerX: number, pointerY: number) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { resetControlMagnet(root); return; }
  const control = target instanceof Element ? target.closest<HTMLButtonElement>("button:not(:disabled)") : null;
  resetControlMagnet(root, control);
  if (!control || !root.contains(control)) return;
  const bounds = control.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const offsetX = Math.max(-.5, Math.min(.5, (pointerX - bounds.left) / bounds.width - .5));
  const offsetY = Math.max(-.5, Math.min(.5, (pointerY - bounds.top) / bounds.height - .5));
  control.style.setProperty("--control-x", offsetX * 12 + "px");
  control.style.setProperty("--control-y", offsetY * 9 + "px");
  control.setAttribute("data-magnetic", "true");
}
