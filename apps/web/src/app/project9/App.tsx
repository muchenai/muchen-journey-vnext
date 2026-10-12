"use client";

import { FormEvent, MouseEvent, useState, useEffect, useId, useRef, useLayoutEffect, CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { effectiveCharacterCount } from "@/lib/text-length";
import { clientLoginErrorMessage, isFeishuClient, loginInsideFeishu } from "@/lib/feishu-client-login";
import { ExecutionDetail, ExecutionView, TaskCards, executionTasks } from "./ExecutionPages";
import { DashboardMain } from "./DashboardMain";
import { SelfCheckHistoryDialog } from "./SelfCheckHistoryDialog";
import { TaskFeedbackDialog } from "./TaskFeedbackDialog";
import { readSelfCheckHistory, saveSelfCheck, selfCheckHistoryKey, type SelfCheckRecord } from "./self-check-history";
import { JourneyProvider, useJourney, useTaskStatus, type JourneyContextValue } from "./journey-context";
import { recordOpenedLearningMaterial, confirmIdentity, exchangeInvite, saveSubmissionDraft, startAssignment, startEvidenceRevision, cancelEvidenceRevision, submitAssignment } from "../actions";
 type Screen = "login" | "welcome" | "dashboard" | "tasks" | "detail" | "view";
type PreviewIdentity = string;
export default function App(props: Partial<JourneyContextValue>) {
 const value: JourneyContextValue = { learnerName: "新同学", experience: null, initialScreen: "login", joinPhase: "invite", joinError: "", ...props };
 return <JourneyProvider value={value}><ExperienceScreen /></JourneyProvider>;
}

function ExperienceScreen() {
 const router = useRouter();
 const { learnerName, experience, initialScreen, initialNotice, joinPhase, joinError } = useJourney();
 const taskStatus = useTaskStatus();
 const identity = null;
 const [screen, setScreen] = useState<Screen>(initialScreen);
 const [scale, setScale] = useState<number | null>(null);
 const viewportRef = useRef<HTMLElement>(null);
 const [notice, setNotice] = useState(initialNotice ?? "");
 const [burst, setBurst] = useState<{ x: number; y: number; key: number } | null>(null);
 const [record, setRecord] = useState(experience?.allowedCommands.some(command => command.startsWith("submit"))
   ? experience?.draftBody || experience?.latestSubmissionBody || ""
   : experience?.latestSubmissionBody || "");
 const [choice, setChoice] = useState("");
 const [checked, setChecked] = useState(false);
 const [historyOpen, setHistoryOpen] = useState(false);
 const [feedbackAssignmentId, setFeedbackAssignmentId] = useState<string | null>(null);
 const selectedFeedback = experience?.reviewFeedback?.find(item => item.assignmentId === feedbackAssignmentId);
 const [historyRecords, setHistoryRecords] = useState<SelfCheckRecord[]>([]);
 const [historyError, setHistoryError] = useState("");
 const [submitting, setSubmitting] = useState(false);
 const submissionInFlight = useRef(false);
 const [revisionBusy, setRevisionBusy] = useState(false);
 const revisionInFlight = useRef(false);
 const [submissionReceipt, setSubmissionReceipt] = useState<{ assignmentId: string; status: string } | null>(null);
 const submittedHere = Boolean(submissionReceipt && submissionReceipt.assignmentId === experience?.assignmentId);
 const canSubmit = Boolean(experience?.allowedCommands.some(command => command.startsWith("submit"))) && !submittedHere;
 const submissionStatus = submittedHere ? submissionReceipt?.status : experience?.status;
 const submitLabel = submitting ? "正在提交…"
   : ["SUBMITTED", "IN_REVIEW"].includes(submissionStatus ?? "") ? "已提交，等待审核"
   : submissionStatus === "NEEDS_REVISION" ? "待修改，请点击重新修改"
   : submissionStatus === "COMPLETED" ? "审核已通过"
   : submittedHere ? "已提交" : "提交任务证据";
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
   setRecord(value);
   setChecked(false);
 };
 useLayoutEffect(() => {
   const resize = () => { setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080)); };
   const observer = new ResizeObserver(resize);
   if (viewportRef.current) observer.observe(viewportRef.current);
   window.addEventListener("resize", resize);
   resize();
   return () => { observer.disconnect(); window.removeEventListener("resize", resize); };
 }, []);
 useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 3000); return () => window.clearTimeout(timer); }, [notice]);
 useEffect(() => {
   if (screen !== "dashboard") return;
   const refresh = () => { if (document.visibilityState === "visible") router.refresh(); };
   window.addEventListener("focus", refresh);
   document.addEventListener("visibilitychange", refresh);
   return () => { window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
 }, [screen, router]);
 const navigate = (target: Screen) => { setScreen(target); setNotice(""); };
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
 if (action === "review-feedback") {
   setFeedbackAssignmentId(button.dataset.assignmentId ?? null);
   return;
 }
 if (["novice-village", "ai-academy", "delivery-guild"].includes(action ?? "")) {
   setNotice("该功能正在设计"); return;
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
   if (!experience?.allowedCommands.includes(command) || revisionInFlight.current || submissionInFlight.current || submittedHere) return;
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
   if (submissionInFlight.current || !canSubmit) return;
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
       setSubmissionReceipt({ assignmentId: experience!.assignmentId, status: result.assignmentStatus });
       setNotice(result.success);
       router.refresh();
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
 if (action === "mentor-profile") { setNotice(experience?.reviewerDisplayName || "审核人"); return; }
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
   if (!experience) return;
   if (record.trim().length < 10 || record.length > 8000) setNotice("请填写 10–8000 个有效字符");
   else {
     const result = "本地格式自查完成，请复核内容与链接访问权限。尚未连接 AI 服务。";
     try {
       const records = saveSelfCheck(window.localStorage,
         selfCheckHistoryKey(experience.assignmentId, experience.taskVersion),
         { id: crypto.randomUUID(), createdAt: new Date().toISOString(), body: record, result });
       setHistoryRecords(records);
       setHistoryError("");
       setChecked(true);
       setNotice(`${result} 已保存至历史 AI 自查记录。`);
     } catch {
       setNotice("本地格式自查已完成，但历史记录保存失败。请检查浏览器存储权限或空间后重试。");
     }
   }
   return;
 }
 if (action === "execution-history") {
   if (!experience) return;
   setHistoryRecords([]);
   setHistoryError("");
   try {
     setHistoryRecords(readSelfCheckHistory(window.localStorage,
       selfCheckHistoryKey(experience.assignmentId, experience.taskVersion)));
   } catch {
     setHistoryError("历史记录读取失败，请检查浏览器存储权限后重试。原有记录未被覆盖。");
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
 else if (text.includes("开始 AI 自查")) { const minimum = executing ? 10 : 40; if (record.trim().length < minimum) setNotice(`请先填写至少 ${minimum} 个有效字符`); else { setChecked(true); setNotice("本地自查完成：请确认记录包含问题、答案来源和下一步行动。尚未连接 AI 服务。"); } }
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
 if (screen === "login") return <Login key={`${joinPhase}:${joinError}`} />;
 return <main ref={viewportRef} className="design-viewport" data-screen={screen} onClick={click} onPointerMove={event => {
   energizePanels(event.currentTarget, event.clientX, event.clientY);
   if (screen === "dashboard" && event.pointerType === "mouse") magnetizeControl(event.currentTarget, event.target, event.clientX, event.clientY);
 }} onPointerLeave={event => {
   event.currentTarget.querySelectorAll(".holo-panel").forEach(panel => panel.removeAttribute("data-energized"));
   resetControlMagnet(event.currentTarget);
 }}>
 <div className="design-stage" key={screen} style={{ transform: scale === null ? undefined : `translate(-50%, -50%) scale(${scale})` }} data-selection={choice}>
 {screen === "welcome" && <Welcome />}
 {screen === "dashboard" && <Dashboard submitted={submitted} identity={identity} />}
 {screen === "tasks" && <Tasks />}
 {screen === "detail" && (executing ? <ExecutionDetail task={task} openedMaterials={[Boolean(openedMaterials[`${task.id}-material-1`]), Boolean(openedMaterials[`${task.id}-material-2`])]} panelDecoration={<><GradientStroke variant="panel" /><PanelFX /></>} backDecoration={<GradientStroke variant="back" />} /> : <Detail />)}
 {screen === "view" && <ExecutionView task={task} record={record} setRecord={updateExecutionRecord} readOnly={!canSubmit} revisionBusy={revisionBusy} canRevise={!submittedHere && !submitting && experience?.allowedCommands.includes("start_evidence_revision")} canCancelRevision={!submittedHere && !submitting && experience?.allowedCommands.includes("cancel_evidence_revision")} submitting={submitting} submitDisabled={submitting || revisionBusy || !canSubmit} submitLabel={submitLabel} panelDecoration={<><GradientStroke variant="panel" /><PanelFX /></>} backDecoration={<GradientStroke variant="back" />} />}
 </div>
 {historyOpen && task && <SelfCheckHistoryDialog title={task.title} records={historyRecords} error={historyError} onClose={() => setHistoryOpen(false)} />}
 {selectedFeedback && <TaskFeedbackDialog feedback={selectedFeedback} title={executionTasks[selectedFeedback.position - 1]?.title ?? selectedFeedback.title} onClose={() => setFeedbackAssignmentId(null)} />}
 {burst && <ClickBurst key={burst.key} x={burst.x} y={burst.y} onFinish={() => setBurst(null)} />}
 {notice && <div role="status" className="fixed bottom-6 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 rounded-xl border border-cyan-300 bg-[#041a35]/95 px-6 py-3 text-center text-sm text-cyan-100 shadow-lg">{notice}</div>}
 </main>;
}

const assetPathPrefix = '/assets/project9'
const logo = `${assetPathPrefix}/6f233.png`
const mission = `${assetPathPrefix}/c21d5.png`
const exploreFrame = `${assetPathPrefix}/baa53.png`
const loginArrow = `${assetPathPrefix}/42137.svg`

function Login() {
  const { joinPhase, joinError } = useJourney();
  const [scale, setScale] = useState<number | null>(null)
  const [language, setLanguage] = useState<'简体中文' | 'English'>('简体中文')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [message, setMessage] = useState(joinError)
  const [isLaunched, setIsLaunched] = useState(false)
  useEffect(() => {
    if (joinPhase !== 'feishu' || joinError || !isFeishuClient(navigator.userAgent)) return;
    let active = true;
    // Defer one tick so React Strict Mode can cancel its first effect setup.
    const timer = window.setTimeout(() => {
      setIsLaunched(true);
      setMessage('正在使用当前飞书账号登录…');
      void loginInsideFeishu().catch(error => {
        if (!active) return;
        setIsLaunched(false);
        setMessage(clientLoginErrorMessage(error));
      });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [joinPhase, joinError]);
  useLayoutEffect(() => {
    const resize = () => setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080))
    window.addEventListener('resize', resize)
    resize()
    return () => window.removeEventListener('resize', resize)
  }, [])

  const launch = async (event: FormEvent) => {
    event.preventDefault()
    if (joinPhase === 'feishu') {
      if (isLaunched) return;
      setIsLaunched(true);
      if (isFeishuClient(navigator.userAgent)) {
        setMessage('正在获取飞书授权…');
        try {
          await loginInsideFeishu();
        } catch (error) {
          setIsLaunched(false);
          setMessage(clientLoginErrorMessage(error));
        }
        return;
      }
      setMessage('正在前往飞书授权…');
      window.location.assign('/auth/feishu?return_to=%2Fapp');
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
      <div className="cosmos-background" aria-hidden="true" />
      <div className="atmosphere atmosphere-one" aria-hidden="true" />
      <div className="atmosphere atmosphere-two" aria-hidden="true" />
      <div className="starfield" aria-hidden="true" />
      <main className={`cosmos-shell login-stage ${isLaunched ? 'is-launched' : ''}`} style={{ transform: scale === null ? undefined : `translate(-50%, -50%) scale(${scale})` }}>

      <header className="topbar">
        <button className="brand-mark" onClick={() => setMessage('欢迎回到沐晨新手村')} aria-label="返回首页">
          <img src={logo} alt="" />
          <span>
            <strong>MUCHEN JOURNEY</strong>
            <small>以成长·速接更大的你<br />A BIGGER YOU A BRIGHTER TOMORROW</small>
          </span>
        </button>
        <nav className="navigation" aria-label="页面工具">
          <button className="nav-control" onClick={() => setLanguage(language === '简体中文' ? 'English' : '简体中文')}>
            <span className="orbit-dot">◉</span>{language}
          </button>
          <i />
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

        <form className="login-panel login-gradient-border" onSubmit={launch}>
          <GradientStroke variant="back" strokeWidth={1} animated={false} />
          <div className="panel-glow" aria-hidden="true" />
          <img className="panel-logo" src={logo} alt="" />
          <p className="panel-title">MUCHEN JOURNEY</p>
          {joinPhase === 'feishu' ? <div className="code-field" style={{ color: '#bdeaff', fontSize: 22, justifyContent: 'center' }}>使用飞书账号，开启你的成长旅程</div> : <label className={`code-field ${(joinPhase === 'invite' ? code : name) ? 'filled' : ''}`}>
            <span className="sr-only">{joinPhase === 'invite' ? '邀请码' : '昵称'}</span>
            {joinPhase === 'invite' ? <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="请输入邀请码" autoComplete="one-time-code" /> : <input value={name} onChange={(event) => setName(event.target.value)} placeholder="请输入昵称" autoComplete="nickname" />}
          </label>}
          <button className="launch-button" type="submit" onMouseMove={magneticMove} onMouseLeave={resetMagnet}>
            <img src={loginArrow} alt="" />
            <span>{joinPhase === 'feishu' ? '使用飞书登录' : '登录并开始探索'}</span>
            <b aria-hidden="true" />
          </button>
          <div className="status-line" role="status">{message}</div>
        </form>
      </section>

      <footer><span>AI 驱动成长 - 连接真实世界</span><span>——————探索·实践·成长·创造更大的价值</span></footer>
      </main>
    </div>
  )
}

function Dashboard({ submitted, identity }: { submitted: boolean; identity: PreviewIdentity | null }) {
const { experience, learnerName } = useJourney();
const taskStatus = useTaskStatus();
const [, refreshRecords] = useState(0);
useEffect(() => {
  const refresh = () => refreshRecords(value => value + 1);
  window.addEventListener("storage", refresh);
  return () => window.removeEventListener("storage", refresh);
}, []);
const activityRecords = experience?.activityRecords ?? [];
const completed = experience?.completedStages ?? 0;
const inProgress = executionTasks.filter((_, index) => taskStatus(index) === "active").length;
const pending = activityRecords.filter(item => ["SUBMITTED", "IN_REVIEW"].includes(item.status))
  .map(item => ({ task: executionTasks[item.position - 1], index: item.position - 1,
    evidence: { record: item.body, submittedAt: item.submittedAt } }))
  .filter(item => item.task)
  .sort((a, b) => Date.parse(b.evidence.submittedAt) - Date.parse(a.evidence.submittedAt));
const feedback = experience?.reviewFeedback ?? [];
const streak = 0;
const formatRecordDate = (date: string) => new Date(date).toLocaleString("zh-CN", {
  month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
const assetPathPrefix = "/assets/project9";
const img46 = `${assetPathPrefix}/04543.png`;
const imgImage44 = `${assetPathPrefix}/6f233.png`;
const imgImage67 = `${assetPathPrefix}/96be2.png`;
const imgImage62 = `${assetPathPrefix}/82501.png`;
const imgImage77 = `${assetPathPrefix}/d6a61.png`;
const imgImage79 = `${assetPathPrefix}/0ccf1.png`;
const imgIcon = `${assetPathPrefix}/3ba37.svg`;
const imgIcon1 = `${assetPathPrefix}/69feb.svg`;
const imgIcon2 = `${assetPathPrefix}/79dce.svg`;
const imgRectangle50 = `${assetPathPrefix}/048f7.svg`;
const imgRectangle60 = `${assetPathPrefix}/a1566.svg`;
const imgRectangle61 = `${assetPathPrefix}/8e84d.svg`;
const imgFrame = `${assetPathPrefix}/eec40.svg`;
const imgEllipse1 = `${assetPathPrefix}/ab5ac.svg`;
const imgFrame1 = `${assetPathPrefix}/4fc5a.svg`;
const imgEllipse2 = `${assetPathPrefix}/29dd9.svg`;
const imgFrame2 = `${assetPathPrefix}/643cc.svg`;
const imgFrame3 = `${assetPathPrefix}/0c76d.svg`;
const imgLine1 = `${assetPathPrefix}/17286.svg`;
const imgFrame4 = `${assetPathPrefix}/f4e78.svg`;
const imgLine2 = `${assetPathPrefix}/04604.svg`;
const imgVectorStroke = `${assetPathPrefix}/a49bf.svg`;
const imgFrame5 = `${assetPathPrefix}/11489.svg`;
const imgEllipse3 = `${assetPathPrefix}/40565.svg`;
const imgEllipse4 = `${assetPathPrefix}/54dd9.svg`;
const imgVector = `${assetPathPrefix}/0b3ec.svg`;
const imgLine3 = `${assetPathPrefix}/29038.svg`;
const imgRectangle64 = `${assetPathPrefix}/0b881.svg`;
const imgFrame6 = `${assetPathPrefix}/7545d.svg`;
const imgEllipse5 = `${assetPathPrefix}/cfbf2.svg`;
const imgVector1 = `${assetPathPrefix}/608f9.svg`;
const imgVector2 = `${assetPathPrefix}/63e0c.svg`;
const imgVector3 = `${assetPathPrefix}/cec96.svg`;


  return (
    <div className="content-stretch flex flex-col items-center justify-center relative size-full" data-node-id="2006:3" style={{ backgroundImage: "linear-gradient(203.81643124441072deg, rgb(0, 6, 12) 30.098%, rgb(21, 45, 76) 82.87%, rgb(0, 8, 17) 95.576%), url(\"data:image/svg+xml;utf8,<svg viewBox='0 0 1920 1080' xmlns='http://www.w3.org/2000/svg' preserveAspectRatio='none'><rect x='0' y='0' height='100%' width='100%' fill='url(%23grad)' opacity='1'/><defs><radialGradient id='grad' gradientUnits='userSpaceOnUse' cx='0' cy='0' r='10' gradientTransform='matrix(0 -106.96 -190.15 0 1305.6 302.4)'><stop stop-color='rgba(11,67,132,1)' offset='0'/><stop stop-color='rgba(9,51,103,1)' offset='0.135'/><stop stop-color='rgba(6,35,73,1)' offset='0.27'/><stop stop-color='rgba(3,19,41,1)' offset='0.63'/></radialGradient></defs></svg>\"), linear-gradient(180deg, rgb(4, 24, 46) 0%, rgb(2, 14, 30) 100%)" }} data-name="学习成长中枢">
      <div className="h-[1080px] relative shrink-0 w-full" data-node-id="2006:4" data-name="Container">
        <div className="absolute contents left-0 top-0" data-node-id="2006:5">
          <div className="absolute h-[1080px] left-0 top-0 w-[1920px]" data-node-id="2006:6" data-name="4 6">
            <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={img46} />
          </div>
        </div>
        <div className="absolute content-stretch flex h-[82px] items-center justify-end left-[1551px] pr-[32px] top-0 w-[369px]" data-node-id="2006:7" data-name="Header">
          <div className="content-stretch flex gap-[36px] items-center relative shrink-0" data-node-id="2006:8" data-name="Container">
            <div className="content-stretch flex h-[27px] items-start relative shrink-0" data-node-id="2006:9">
              <button type="button" data-action="true" className="relative shrink-0 size-[26.857px]" data-node-id="2006:10" data-name="Icon">
                <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgIcon} />
              </button>
            </div>
            <button type="button" data-action="true" className="relative shrink-0 size-[26.286px]" data-node-id="2006:13" data-name="Icon">
              <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgIcon1} />
            </button>
            <button type="button" data-action="true" className="content-stretch flex gap-[11.429px] items-center relative shrink-0" data-node-id="2006:15" data-name="Container">
              <div className="border-[#86bbdf] border-[1.143px] border-solid grid grid-cols-[_41.14px] grid-rows-[_41.14px] relative rounded-[21.714px] shrink-0 size-[43.429px]" data-node-id="2006:16" style={{ backgroundImage: "linear-gradient(145.0000003379585deg, rgb(240, 217, 192) 6.1733%, rgb(85, 115, 143) 93.827%)" }} data-name="Container">
                <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] justify-self-center leading-[normal] not-italic relative row-1 self-center shrink-0 text-[#09223c] text-[14.857px] whitespace-nowrap font-black" data-node-id="2006:17">
                  {Array.from(learnerName.trim())[0] || "新"}
                </p>
              </div>
              <div className="content-stretch flex flex-col items-start relative shrink-0 w-[89.143px]" data-node-id="2006:18" data-name="Container">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] min-w-full not-italic relative shrink-0 text-[#eff6ff] text-[14.857px] w-[min-content] font-bold" data-node-id="2006:19">
                  {learnerName}
                </p>
                <div className="content-stretch flex flex-col h-[20.571px] items-start pt-[3.429px] relative shrink-0 w-[89.143px]" data-node-id="2006:20" data-name="Small">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#8ba8c6] text-[12.571px] whitespace-nowrap" data-node-id="2006:21">
                    继续朝前进吧!
                  </p>
                </div>
              </div>
              <div className="relative shrink-0 size-[13.714px]" data-node-id="2006:22" data-name="Icon">
                <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgIcon2} />
              </div>
            </button>
          </div>
        </div>
        <div className="absolute bg-gradient-to-b border-[rgba(47,99,153,0.32)] border-r-[1.143px] border-solid content-stretch flex flex-col from-[rgba(3,18,37,0.8)] gap-[36px] h-[1080px] items-start left-0 pb-[32px] pt-[20.571px] px-[18.286px] to-[rgba(3,16,31,0.55)] top-0 w-[338px]" data-node-id="2006:24" data-name="Sidebar">
          <div className="content-stretch flex flex-col gap-[52px] items-start relative shrink-0" data-node-id="2006:25">
            <div className="content-stretch flex flex-col gap-[9px] items-center justify-center px-[15px] relative shrink-0" data-node-id="2006:26" data-name="Container">
              <div className="content-stretch flex items-center justify-center pb-[5.714px] relative shrink-0 w-[229.714px]" data-node-id="2006:27" data-name="Heading 1:margin">
                <div className="relative shrink-0 size-[84px]" data-node-id="2006:28" data-name="image 44">
                  <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage44} />
                </div>
                <div className="content-stretch flex flex-[1_0_0] flex-col items-start min-w-px relative" data-node-id="2006:29" data-name="Heading 1">
                  <div className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[0] not-italic relative shrink-0 text-[29.085px] tracking-[1.0387px] whitespace-nowrap font-black dashboard-brand-gradient" data-node-id="2006:30">
                    <p className="font-['Source_Han_Sans_SC'] mb-0 whitespace-pre">
                      <span className="leading-[29.085px] tracking-[2.2px]">{` MUCHEN`}</span>
                      <span className="leading-[29.085px]">{` `}</span>
                    </p>
                    <p className="font-['Source_Han_Sans_SC'] leading-[29.085px] whitespace-pre">JOURNEY</p>
                  </div>
                </div>
              </div>
              <div className="h-[12px] relative shrink-0 w-[210px]" data-node-id="2006:31" data-name="Small:margin">
                <div className="absolute content-stretch flex flex-col items-start left-0 top-0 w-[229.714px]" data-node-id="2006:32" data-name="Small">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[14.26px] not-italic relative shrink-0 text-[#6388b0] text-[14.26px] tracking-[5.7039px] w-[271px]" data-node-id="2006:33">
                    从这里，走向更大的自己
                  </p>
                </div>
              </div>
            </div>
            <div className="content-stretch flex flex-col gap-[18px] items-start leading-[0] relative shrink-0 w-[302px]" data-node-id="2006:34">
              <button type="button" data-action="true" className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0" data-node-id="2006:35">
                <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2006:36">
                  <div className="col-1 h-[108px] ml-0 mt-0 relative row-1 w-[302px]" data-node-id="2006:37">
                    <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgRectangle50} />
                  </div>
                  <div className="col-1 h-[108px] ml-[65px] mt-0 relative rounded-[16px] row-1 w-[237px]" data-node-id="2006:38" data-name="image 67">
                    <div className="absolute inset-0 opacity-66 overflow-hidden pointer-events-none rounded-[16px]">
                      <img alt="" className="absolute h-[329.8%] left-[-7.87%] max-w-none top-[-46.98%] w-[265.91%]" src={imgImage67} />
                    </div>
                  </div>
                  <div className="bg-gradient-to-r col-1 from-[#07101f] h-[108px] ml-0 mt-0 relative rounded-[16px] row-1 to-[rgba(0,0,0,0)] w-[150px]" data-node-id="2006:39" />
                  <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 h-[108px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 shadow-[0px_4px_28.4px_0px_rgba(91,63,255,0.6)] w-[302px] figma-stroke figma-stroke-active" data-node-id="2006:40"><GradientStroke variant="active" />
                    <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(258.993646731062deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.49) 34.784%, rgba(7, 5, 134, 0.377) 68.342%, rgba(10, 0, 153, 0.49) 90.024%)" }} />
                    <div className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
                  </div>
                </div>
                <div className="col-1 content-stretch flex gap-[46px] items-center ml-[19px] mt-[26px] relative row-1" data-node-id="2006:41">
                  <div className="content-stretch flex gap-[23px] items-center relative shrink-0" data-node-id="2006:42">
                    <div className="h-[56px] relative shrink-0 w-[57px]" data-node-id="2006:43" data-name="image 62">
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <img alt="" className="absolute h-[200%] left-[-31.29%] max-w-none top-[-1.24%] w-[296.3%]" src={imgImage62} />
                      </div>
                    </div>
                    <div className="[word-break:break-word] content-stretch flex flex-col gap-[7px] items-start leading-[normal] not-italic relative shrink-0 w-[124px]" data-node-id="2006:44">
                      <p className="font-['Source_Han_Sans_SC'] relative shrink-0 text-[21px] text-white w-full font-medium" data-node-id="2006:45">
                        探索营
                      </p>
                      <p className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[15.5px] w-full" data-node-id="2006:46">
                        欢迎尽情探索
                      </p>
                    </div>
                  </div>
                  <div className="flex h-[14.877px] items-center justify-center relative shrink-0 w-[14.88px]" data-node-id="2006:47">
                    <div className="flex-none rotate-[45.97deg]">
                      <div className="h-[10.593px] relative w-[10.451px]">
                        <div className="absolute inset-[-9.44%_-9.57%]">
                          <img alt="" className="block max-w-none size-full" src={imgRectangle60} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </button>
              <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0" data-node-id="2006:48">
                <button type="button" data-action="novice-village" className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2006:49">
                  <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2006:50">
                    <div className="border-[#3a3e91] border-[1.6px] border-solid col-1 h-[108px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[302px] figma-stroke figma-stroke-idle" data-node-id="2006:51"><GradientStroke variant="idle" />
                      <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(90.50703005098474deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)" }} />
                      <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-71px_-13px_51.4px_2px_rgba(22,89,130,0.32)]" />
                    </div>
                  </div>
                  <div className="col-1 content-stretch flex items-center ml-[18px] mt-[25px] relative row-1" data-node-id="2006:52">
                    <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:53">
                      <div className="col-1 content-stretch flex gap-[23px] items-center ml-0 mt-0 relative row-1" data-node-id="2006:54">
                        <div className="relative shrink-0 size-[58px]" data-node-id="2006:55" data-name="image 63">
                          <div className="absolute inset-0 overflow-hidden pointer-events-none">
                            <img alt="" className="absolute h-[200%] left-[-163.61%] max-w-none top-[-3.74%] w-[296.3%]" src={imgImage62} />
                          </div>
                        </div>
                        <div className="[word-break:break-word] content-stretch flex flex-col gap-[7px] items-start leading-[normal] not-italic relative shrink-0 w-[124px]" data-node-id="2006:56">
                          <p className="font-['Source_Han_Sans_SC'] relative shrink-0 text-[21px] text-white w-full font-medium" data-node-id="2006:57">
                            新手村
                          </p>
                          <p className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[15.5px] w-full whitespace-nowrap" data-node-id="2006:58">
                            开启你的成长地图
                          </p>
                        </div>
                      </div>
                      <div className="col-1 flex h-[14.877px] items-center justify-center ml-[251px] mt-[21.56px] relative row-1 w-[14.88px]" data-node-id="2006:59">
                        <div className="flex-none rotate-[45.97deg]">
                          <div className="h-[10.593px] relative w-[10.451px]">
                            <div className="absolute inset-[-9.44%_-9.57%]">
                              <img alt="" className="block max-w-none size-full" src={imgRectangle61} />
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </button>
              </div>
              <button type="button" data-action="ai-academy" className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0" data-node-id="2006:60">
                <div className="border-[#3a3e91] border-[1.6px] border-solid col-1 h-[108px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[302px] figma-stroke figma-stroke-idle" data-node-id="2006:61"><GradientStroke variant="idle" />
                  <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(90.50703005098474deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)" }} />
                  <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-71px_-13px_51.4px_2px_rgba(22,89,130,0.32)]" />
                </div>
                <div className="col-1 content-stretch flex gap-[46px] items-center ml-[18px] mt-[25px] relative row-1" data-node-id="2006:62">
                  <div className="content-stretch flex gap-[23px] items-center relative shrink-0" data-node-id="2006:63">
                    <div className="h-[57px] relative shrink-0 w-[58px]" data-node-id="2006:64" data-name="image 64">
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <img alt="" className="absolute h-[200%] left-[-31.29%] max-w-none top-[-95.3%] w-[296.3%]" src={imgImage62} />
                      </div>
                    </div>
                    <div className="[word-break:break-word] content-stretch flex flex-col gap-[7px] items-start leading-[normal] not-italic relative shrink-0 w-[124px]" data-node-id="2006:65">
                      <p className="font-['Source_Han_Sans_SC'] relative shrink-0 text-[21px] text-white w-full font-medium" data-node-id="2006:66">
                        AI学院
                      </p>
                      <p className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[15.5px] w-full" data-node-id="2006:67">
                        与AI共创可能
                      </p>
                    </div>
                  </div>
                  <div className="flex h-[14.877px] items-center justify-center relative shrink-0 w-[14.88px]" data-node-id="2006:68">
                    <div className="flex-none rotate-[45.97deg]">
                      <div className="h-[10.593px] relative w-[10.451px]">
                        <div className="absolute inset-[-9.44%_-9.57%]">
                          <img alt="" className="block max-w-none size-full" src={imgRectangle60} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </button>
              <button type="button" data-action="delivery-guild" className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0" data-node-id="2006:69">
                <div className="border-[#3a3e91] border-[1.6px] border-solid col-1 h-[108px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[302px] figma-stroke figma-stroke-idle" data-node-id="2006:70"><GradientStroke variant="idle" />
                  <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(90.50703005098474deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)" }} />
                  <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-71px_-13px_51.4px_2px_rgba(22,89,130,0.32)]" />
                </div>
                <div className="col-1 content-stretch flex gap-[46px] items-center ml-[18px] mt-[25px] relative row-1" data-node-id="2006:71">
                  <div className="content-stretch flex gap-[23px] items-center relative shrink-0" data-node-id="2006:72">
                    <div className="h-[57px] relative shrink-0 w-[58px]" data-node-id="2006:73" data-name="image 65">
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <img alt="" className="absolute h-[200%] left-[-163.61%] max-w-none top-[-99.51%] w-[296.3%]" src={imgImage62} />
                      </div>
                    </div>
                    <div className="[word-break:break-word] content-stretch flex flex-col gap-[7px] items-start leading-[normal] not-italic relative shrink-0 w-[124px]" data-node-id="2006:74">
                      <p className="font-['Source_Han_Sans_SC'] relative shrink-0 text-[21px] text-white w-full font-medium" data-node-id="2006:75">
                        交付线公会
                      </p>
                      <p className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[15.5px] w-full whitespace-nowrap" data-node-id="2006:76">
                        在实践中创造价值
                      </p>
                    </div>
                  </div>
                  <div className="flex h-[14.877px] items-center justify-center relative shrink-0 w-[14.88px]" data-node-id="2006:77">
                    <div className="flex-none rotate-[45.97deg]">
                      <div className="h-[10.593px] relative w-[10.451px]">
                        <div className="absolute inset-[-9.44%_-9.57%]">
                          <img alt="" className="block max-w-none size-full" src={imgRectangle60} />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </button>
            </div>
          </div>
          <div className="content-stretch flex flex-col gap-[28px] items-start pl-[18px] pt-[18px] relative shrink-0 w-[302px]" data-node-id="2006:78">
            <button type="button" data-action="true" className="content-stretch flex gap-[13px] items-center relative shrink-0" data-node-id="2006:79">
              <div className="content-stretch flex gap-[21px] items-center relative shrink-0" data-node-id="2006:80">
                <div className="relative shrink-0 size-[24px]" data-node-id="2006:81" data-name="Frame">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame} />
                </div>
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#8ea1e2] text-[15.5px] whitespace-nowrap" data-node-id="2006:86">
                  我的任务
                </p>
              </div>
              <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:87" hidden={inProgress === 0} aria-label={`${inProgress} 项进行中的任务`}>
                <div className="bg-[#f03751] col-1 ml-0 mt-0 relative rounded-[34.667px] row-1 size-[20px]" data-node-id="2006:88" />
                <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-black leading-[normal] justify-self-center self-center not-italic relative row-1 top-[-3px] text-[12px] text-center text-white whitespace-nowrap" data-node-id="2006:89">
                  {inProgress}
                </p>
              </div>
            </button>
            <button type="button" data-action="true" className="content-stretch flex gap-[13px] items-center relative shrink-0" data-node-id="2006:90">
              <div className="content-stretch flex gap-[21px] items-center relative shrink-0" data-node-id="2006:91">
                <div className="relative shrink-0 size-[24px]" data-node-id="2006:92" data-name="Frame">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame1} />
                </div>
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#8ea1e2] text-[15.5px] whitespace-nowrap" data-node-id="2006:95">
                  团队进度
                </p>
              </div>
              <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:96" hidden>
                <div className="col-1 ml-0 mt-0 relative row-1 size-[24.217px]" data-node-id="2006:97">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse2} />
                </div>
                <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-bold leading-[normal] ml-[7.37px] mt-[2.11px] not-italic relative row-1 text-[16.32px] text-white whitespace-nowrap" data-node-id="2006:98">
                  1
                </p>
              </div>
            </button>
            <button type="button" data-action="true" className="content-stretch flex gap-[21px] items-center relative shrink-0" data-node-id="2006:99">
              <div className="relative shrink-0 size-[24px]" data-node-id="2006:100" data-name="Frame">
                <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame2} />
              </div>
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#8ea1e2] text-[15.5px] whitespace-nowrap" data-node-id="2006:104">
                知识库
              </p>
            </button>
            <button type="button" data-action="true" className="content-stretch flex gap-[21px] items-center relative shrink-0" data-node-id="2006:105">
              <div className="relative shrink-0 size-[24px]" data-node-id="2006:106" data-name="Frame">
                <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame3} />
              </div>
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#8ea1e2] text-[15.5px] whitespace-nowrap" data-node-id="2006:111">
                切换身份
              </p>
            </button>
            <div className="h-0 relative shrink-0 w-full" data-node-id="2006:112">
              <div className="absolute inset-[-1px_0.11%_0_0.11%]">
                <img alt="" className="block max-w-none size-full" src={imgLine1} />
              </div>
            </div>
            <div className="content-stretch flex gap-[21px] items-center relative shrink-0" data-node-id="2006:113">
              <div className="relative shrink-0 size-[24px]" data-node-id="2006:114" data-name="Frame">
                <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame4} />
              </div>
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#8ea1e2] text-[15.5px] whitespace-nowrap" data-node-id="2006:117">
                设置
              </p>
            </div>
            <div className="content-stretch flex items-center justify-center pt-[37px] relative shrink-0" data-node-id="2006:118">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[22.857px] not-italic relative shrink-0 text-[#606fa3] text-[8px] tracking-[2.2857px] w-[284px]" data-node-id="2006:119">
                Better People Better Work A Brighter Tomorrow
              </p>
            </div>
          </div>
        </div>
        <div className="absolute content-stretch flex flex-col gap-[16px] items-start left-[1396.57px] pb-[27.429px] pr-[18.286px] pt-[6px] top-[82.29px] w-[523.429px]" data-node-id="2006:120" data-name="Sidebar">
          <div className="border-2 border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[240px] items-start p-[16px] relative rounded-[18px] shrink-0 w-full figma-stroke figma-stroke-task" data-node-id="2006:121" style={{ backgroundImage: "linear-gradient(267.04662672974655deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section"><GradientStroke variant="task" />
            <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="2006:122" data-name="Heading 3">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[20.571px] whitespace-nowrap font-bold" data-node-id="2006:123">
                探索营进度
              </p>
            </div>
            <div className="content-stretch flex gap-[13.714px] h-[91.773px] items-center pt-[13.714px] relative shrink-0 w-full" data-node-id="2006:124" data-name="Container">
              <div className="content-stretch flex flex-col items-start relative shrink-0 size-[78.059px]" data-node-id="2006:125" data-name="Container:transform">
                <div className="absolute left-[0.43px] size-[78px] top-0" data-node-id="2006:126" data-name="image 77">
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <img alt="" className="absolute h-[349.08%] left-[-51.25%] max-w-none top-[-232.01%] w-[618.44%]" src={imgImage77} />
                  </div>
                </div>
              </div>
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:127" data-name="Bold Text">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#8ed8ff] text-[18.286px] whitespace-nowrap font-bold" data-node-id="2006:128">
                  完成{completed}项
                </p>
              </div>
              <div className="bg-[#152f4d] border-[#6a90af] border-[1.143px] border-solid content-stretch flex flex-[232.484_0_0] flex-col h-[10.286px] items-start min-w-px overflow-clip relative rounded-[5.714px]" data-node-id="2006:129" data-name="Container">
                <div className="bg-gradient-to-r from-[#1eb8e6] h-[8px] relative shadow-[0px_0px_11.429px_0px_#4adfff] shrink-0 to-[#68edff]" style={{ width: `${completed / executionTasks.length * 100}%` }} data-node-id="2006:130" data-name="Italic Text" />
              </div>
              <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:131" data-name="Small">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[15.238px] whitespace-nowrap" data-node-id="2006:132">
                  {completed}/{executionTasks.length}
                </p>
              </div>
            </div>
            <div className="content-stretch flex flex-col items-start pt-[13.714px] relative shrink-0 w-full" data-node-id="2006:133" data-name="Container:margin">
              <div className="gap-x-[10.285713195800781px] gap-y-[10.285713195800781px] grid grid-cols-[___150.09px_150.09px_150.09px] grid-rows-[_65.14px] relative shrink-0 w-full" data-node-id="2006:134" data-name="Container">
                <div className="border-[#274c73] border-[1.143px] border-solid col-1 content-stretch flex flex-col h-[65.143px] items-start justify-self-stretch px-[9.143px] py-[8px] relative rounded-[6.857px] row-1 self-start shrink-0" data-node-id="2006:135" data-name="Container">
                  <div className="h-[16px] relative shrink-0 w-full" data-node-id="2006:136" data-name="Container">
                    <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[normal] left-0 not-italic text-[#a0b7d1] text-[11.429px] top-0 whitespace-nowrap" data-node-id="2006:137">
                      连续学习
                    </p>
                  </div>
                  <div className="content-stretch flex flex-col h-[30.857px] items-start pt-[3.429px] relative shrink-0 w-[129.518px]" data-node-id="2006:138" data-name="Bold Text">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[0] not-italic relative shrink-0 text-[#ffd65d] text-[0px] whitespace-nowrap font-bold" data-node-id="2006:139">
                      <span className="leading-[normal] text-[20.571px]">{streak} </span>
                      <span className="leading-[normal] text-[13.714px] text-white">天</span>
                    </p>
                  </div>
                </div>
                <div className="border-[#274c73] border-[1.143px] border-solid col-2 content-stretch flex flex-col h-[65.143px] items-start justify-self-stretch px-[9.143px] py-[8px] relative rounded-[6.857px] row-1 self-start shrink-0" data-node-id="2006:140" data-name="Container">
                  <div className="h-[17.143px] relative shrink-0 w-full" data-node-id="2006:141" data-name="Container">
                    <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[normal] left-0 not-italic text-[#a0b7d1] text-[11.429px] top-[1.14px] whitespace-nowrap" data-node-id="2006:142">
                      ▥ 完成任务
                    </p>
                  </div>
                  <div className="content-stretch flex flex-col h-[30.857px] items-start pt-[3.429px] relative shrink-0 w-[129.518px]" data-node-id="2006:143" data-name="Bold Text">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[0] not-italic relative shrink-0 text-[#ffd65d] text-[0px] whitespace-nowrap font-bold" data-node-id="2006:144">
                      <span className="leading-[normal] text-[20.571px]">{completed} </span>
                      <span className="leading-[normal] text-[13.714px] text-white">个</span>
                    </p>
                  </div>
                </div>
                <div className="border-[#274c73] border-[1.143px] border-solid col-3 content-stretch flex flex-col h-[65.143px] items-start justify-self-stretch px-[9.143px] py-[8px] relative rounded-[6.857px] row-1 self-start shrink-0" data-node-id="2006:145" data-name="Container">
                  <div className="h-[16px] relative shrink-0 w-full" data-node-id="2006:146" data-name="Container">
                    <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] leading-[normal] left-0 not-italic text-[#a0b7d1] text-[11.429px] top-0 whitespace-nowrap" data-node-id="2006:147">
                      ♛ 累计获得经验
                    </p>
                  </div>
                  <div className="content-stretch flex flex-col h-[30.857px] items-start pt-[3.429px] relative shrink-0 w-[129.518px]" data-node-id="2006:148" data-name="Bold Text">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#ffd65d] text-[20.571px] whitespace-nowrap font-bold" data-node-id="2006:149">
                      {completed * 100} 经验
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="border-2 border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[300px] items-start p-[16px] relative rounded-[18px] shrink-0 w-full figma-stroke figma-stroke-task" data-node-id="2006:150" style={{ backgroundImage: "linear-gradient(267.6365480293373deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section"><GradientStroke variant="task" />
            <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="2006:151" data-name="Heading 3">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[20.571px] whitespace-nowrap font-bold" data-node-id="2006:152">
                待审核任务 · {pending.length}
              </p>
            </div>
            <div className="dashboard-records" data-node-id="2006:153">
              {pending.length === 0 ? <p className="dashboard-record-empty">暂无待审核任务，提交任务后将在这里显示。</p> : pending.map(({ task, index, evidence }) => <div className="dashboard-record" key={task.id}>
                <button type="button" className="dashboard-record-title" data-action="open-task" data-task-index={index}>{task.title} →</button>
                <div className="dashboard-record-meta"><time dateTime={evidence.submittedAt}>{formatRecordDate(evidence.submittedAt)} 提交</time><span>待审核</span></div>
                <p className="dashboard-record-preview">{evidence.record}</p>
              </div>)}
            </div>
          </div>
          <div className="border-2 border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[382px] items-start p-[16px] relative rounded-[18px] shrink-0 w-full figma-stroke figma-stroke-task" data-node-id="2006:163" style={{ backgroundImage: "linear-gradient(268.14348240385027deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section"><GradientStroke variant="task" />
            <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="2006:164" data-name="Heading 3">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[20.571px] whitespace-nowrap font-bold" data-node-id="2006:165">
                任务反馈
              </p>
            </div>
            <div className="dashboard-records" data-node-id="2006:166">
              {feedback.length === 0 ? <p className="dashboard-record-empty">暂无审核反馈，审核人员完成审核后将在这里显示。</p> : feedback.map(entry => <button
                type="button" className="dashboard-record task-feedback-entry" key={entry.assignmentId}
                data-action="review-feedback" data-assignment-id={entry.assignmentId} aria-haspopup="dialog">
                <span className="dashboard-record-title">{executionTasks[entry.position - 1]?.title ?? entry.title} →</span>
                <span className="dashboard-record-meta"><strong>{entry.records[0].decision === "PASS" ? "审核通过" : "退回修改"}</strong><time dateTime={entry.records[0].reviewedAt}>{formatRecordDate(entry.records[0].reviewedAt)}</time></span>
                <span className="task-feedback-hint">查看完整反馈 · 共 {entry.records.length} 条记录</span>
              </button>)}
            </div>
          </div>
        </div>
        <div className="absolute h-0 left-[18px] top-[159px] w-[302px]" data-node-id="2006:178">
          <div className="absolute inset-[-1px_0.1%_0_0.1%]">
            <img alt="" className="block max-w-none size-full" src={imgLine2} />
          </div>
        </div>
        <DashboardMain identity={identity} decoration={<GradientStroke variant="task" />} stageDecoration={<GradientStroke variant="active" strokeWidth={1.006} animated={false} />} />
      </div>
    </div>
  );
}
function Tasks() {
const { learnerName, experience } = useJourney();
const taskStatus = useTaskStatus();
const completed = executionTasks.filter((_, index) => taskStatus(index) === "completed").length;
const current = executionTasks[(experience?.currentStagePosition ?? 1) - 1];
const assetPathPrefix = "/assets/project9";
const imgImage74 = `${assetPathPrefix}/90975.png`;
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
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px]" style={{ backgroundImage: "linear-gradient(264.5013758981721deg, rgba(0, 50, 91, 0.41) 2.4688%, rgba(36, 77, 132, 0.169) 14.255%, rgba(0, 7, 55, 0.34) 44.37%, rgba(7, 1, 94, 0.41) 90.024%)" }} />
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
            <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2006:330" data-name="Small">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] leading-[22px] not-italic relative shrink-0 text-[#779ab8] text-[13.333px] text-right whitespace-nowrap" data-node-id="2006:331">
                旅程版本 V5
              </p>
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
              <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(255.0525143236887deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.407) 44.37%, rgba(10, 0, 153, 0.49) 90.024%)" }} />
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
function Detail() {const { learnerName } = useJourney();
const assetPathPrefix = "/assets/project9";
const imgImage74 = `${assetPathPrefix}/90975.png`;
const imgRectangle60 = `${assetPathPrefix}/59316.svg`;


  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-node-id="2006:462" data-name="任务详情">
      <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2006:463">
        <div className="col-1 h-[1080px] ml-0 mt-0 relative row-1 w-[1920px]" data-node-id="2006:464" data-name="image 74">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage74} />
        </div>
        <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 content-stretch flex flex-col items-start ml-[654px] mt-[86px] p-[24px] relative rounded-[16px] row-1 shadow-[0px_0px_39.9px_0px_rgba(0,112,191,0.66)] w-[1180px] figma-stroke figma-stroke-panel holo-panel" data-node-id="2006:465" data-name="Section"><GradientStroke variant="panel" /><PanelFX />
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px]" style={{ backgroundImage: "linear-gradient(264.5472023483291deg, rgba(0, 50, 91, 0.41) 2.4688%, rgba(36, 77, 132, 0.169) 14.255%, rgba(0, 7, 55, 0.34) 44.37%, rgba(7, 1, 94, 0.41) 90.024%)" }} />
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
              <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(255.0525143236887deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.407) 44.37%, rgba(10, 0, 153, 0.49) 90.024%)" }} />
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
const { learnerName } = useJourney();
return <div className="relative h-[1080px] w-[1920px] text-[#f2fcff]" data-node-id="2006:578">
<img src="/assets/project9/90975.png" alt="" className="absolute inset-0 h-full w-full object-cover" />
<button type="button" data-action="true" data-node-id="2006:590" className="welcome-back figma-stroke figma-stroke-back absolute left-[114px] top-[105px] h-[68px] w-[261px] rounded-[16px] border-[1.6px] border-transparent">
  <div aria-hidden="true" className="absolute inset-0 rounded-[16px] bg-[linear-gradient(255.0525143236887deg,rgba(201,231,255,0.49)_2.4688%,rgba(52,113,195,0.202)_14.255%,rgba(1,14,105,0.407)_44.37%,rgba(10,0,153,0.49)_90.024%)]" />
  <div aria-hidden="true" className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
  <GradientStroke variant="back" />
  <span className="absolute left-[20px] top-[19px] flex w-[221.245px] items-center justify-center gap-[24px]">
    <span aria-hidden="true" className="relative flex h-[20.956px] w-[20.961px] shrink-0 items-center justify-center">
      <span className="-scale-y-100 rotate-[134.03deg]"><span className="relative block h-[14.922px] w-[14.722px]"><span className="absolute inset-[-6.7%_-6.79%]"><img src="/assets/project9/59316.svg" alt="" className="block max-w-none" /></span></span></span>
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
    <span aria-hidden="true" className="relative h-[27.234px] w-[23.83px] shrink-0"><img src="/assets/project9/37de3.svg" alt="" className="absolute inset-0 block max-w-none" /></span>
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
  // Keep the server render and first browser render identical. Motion
  // preferences are applied by the client-only effect below.
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
    if (preference.matches) timer = window.setTimeout(() => setRevealed(total), 0);
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
      const start = welcomeParagraphs.slice(0, paragraphIndex).reduce((sum, value) => sum + Array.from(value).length, 0);
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
