import { BadgeShop } from "./BadgeShop"
import { TaskClassifications } from "./TaskClassifications"
import { filterDepartmentTasks, taskDepartmentName, type TaskDepartmentFilter } from "./taskDepartments"
import { useVillageTasks, type VillageTask } from "./useVillageTasks"
import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { sharedAsset } from "./sharedAsset"
import type { PreviewIdentity } from "./previewStorage"
import { useCanvasScale } from "./useCanvasScale"
import { WelcomeNameDialog } from "./WelcomeNameDialog"
import { saveLearnerNickname } from "../actions"
import {

  moduleTitles,


  type AcademyCourse,
  type ModuleName,

} from "./moduleDemoData"
import {
  ModuleBorderProvider,
  ModuleHero,
  ModuleHeader,
  ModuleIcon,
  ModulePanel,
  ModuleSidebar,
  ModuleStatus,
  type ModuleDestination,
  type ModuleStatusName,
} from "./ModuleShell"
import { VillageTaskCard, VillageTaskRewards } from "./VillageTaskCard"
import { JourneyDialogSurface } from "./JourneyDialogSurface"
import { AccountSwitchDialog } from "./AccountSwitchDialog"
import { PersonalProfile } from "./PersonalProfile"
import { WorldMap } from "./WorldMap"
import { KnowledgeLibrary } from "./KnowledgeLibrary"
import { FavoriteKnowledge, KnowledgeSaveButton } from "./FavoriteKnowledge"
import "./favoriteKnowledge.css"
import { ModuleCourseArtwork } from "./ModuleCourseArtwork"
import "./moduleHub.css"

const academyCourses: AcademyCourse[] = [];


type PracticeState = { status: ModuleStatusName; answer: string }
type DialogState = { type: "task"; task: VillageTask } | {
  type: "course"
  course: AcademyCourse
} | { type: "info"; title: string; body: string } | { type: "share" } | null

export function ModuleHub({
  active = true,
  module,
  identity,
  onNavigate,
  decoration,
  activeNavigationDecoration,
  idleNavigationDecoration,
  dashboardContent,
  onExplorationMenu,
  explorationTaskCount = 0,
  nicknameRequired = false,
}: {
  active?: boolean
  module: ModuleDestination
  identity: PreviewIdentity
  onNavigate: (destination: ModuleDestination) => void
  decoration: ReactNode
  activeNavigationDecoration: ReactNode
  idleNavigationDecoration: ReactNode
  dashboardContent?: ReactNode
  onExplorationMenu: (menu: string) => void
  explorationTaskCount?: number
  nicknameRequired?: boolean
}) {
  const villageEnabled = module === "village"
  const modulePagesEnabled = ["academy", "guild"].includes(module)
  const village = useVillageTasks(villageEnabled)
  const practiceTasks = village.tasks
  const canvasScale = useCanvasScale()
  const [menu, setMenu] = useState("hall")
  const [profileReturn, setProfileReturn] = useState("hall")
  const [accountSwitchOpen, setAccountSwitchOpen] = useState(false)
  const displayName = identity
  const [taskDepartment, setTaskDepartment] = useState<TaskDepartmentFilter>("all")
  const [taskLevel, setTaskLevel] = useState("全部")
  const [taskReview, setTaskReview] = useState("全部")
  const [taskBadgeType, setTaskBadgeType] = useState("全部")
  const resetTaskFilters = () => {setTaskDepartment("all"); setTaskLevel("全部"); setTaskReview("全部"); setTaskBadgeType("全部"); setQuery("")}
  const [filter, setFilter] = useState("全部")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState("recommended")
  const [practice, setPractice] = useState<Record<string, PracticeState>>({})
  const [favorites] = useState<string[]>([])
  const [learned] = useState<string[]>([])
  const [dialog, setDialog] = useState<DialogState>(null)
  const [notice, setNotice] = useState("")
  const [guild, setGuild] = useState("PM")
  const [shared] = useState<{ title: string; url: string }[]>([])
  const modal = useRef<HTMLDialogElement>(null)
  const listing = useRef<HTMLDivElement>(null)
  const pageContent = useRef<HTMLDivElement>(null)
  const pendingMapTaskScroll = useRef(false)
  const openMapDepartmentTasks = useCallback((department: TaskDepartmentFilter) => {
    if (module !== "village") return
    setMenu("hall")
    setTaskDepartment(department)
    setTaskLevel("全部")
    setTaskReview("全部")
    setTaskBadgeType("全部")
    setQuery("")
    setFilter("全部")
    setSort("recommended")
    setDialog(null)
    setNotice("")
    pendingMapTaskScroll.current = true
  }, [module, setQuery, setFilter])
  useLayoutEffect(() => {
    if (menu !== "hall" || !pendingMapTaskScroll.current) return
    pendingMapTaskScroll.current = false
    if (listing.current && pageContent.current) pageContent.current.scrollTo({
      top: listing.current.offsetTop - pageContent.current.offsetTop - 24,
      behavior: "auto",
    })
  }, [menu])
  useEffect(() => {
    const initial = window.setTimeout(() => {
      setMenu("hall")
      resetTaskFilters()
      setFilter("全部")
      setQuery("")
      setSort("recommended")
      setDialog(null)
      setNotice("")
      pageContent.current?.scrollTo({ top: 0 })
    }, 0)
    return () => window.clearTimeout(initial)
  }, [module])
  useEffect(() => {
    if (dialog) modal.current?.showModal()
    else modal.current?.close()
  }, [dialog])
  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(""), 4500)
    return () => window.clearTimeout(timeout)
  }, [notice])
  const taskStatus = (id: string): ModuleStatusName =>
    practiceTasks.find(task => task.id === id)?.status || "available"
  const accepted = practiceTasks.filter((t) => taskStatus(t.id) !== "available")
  const pending = accepted.filter((t) => taskStatus(t.id) === "pending")
  const completed = accepted.filter((t) => taskStatus(t.id) === "completed")
  const info = (title: string, body: string) => {
    if (villageEnabled || modulePagesEnabled) setDialog({ type: "info", title, body })
    else setNotice("暂未开放")
  }
  const scrollToListing = () => {
    if (!listing.current || !pageContent.current) return
    pageContent.current.scrollTo({
      top: listing.current.offsetTop - pageContent.current.offsetTop - 24,
      behavior: "smooth",
    })
  }
  function navigateMenu(next: string) {
    if (next === "map" || next === "knowledge") {
      setMenu(next)
      setQuery("")
      pageContent.current?.scrollTo({ top: 0 })
      return
    }
    if (module === "dashboard") {
      if (next === "hall") {
        setMenu("hall")
        setQuery("")
      }
      onExplorationMenu(next)
      return
    }
    if (["hall", "mine", "saved"].includes(next)) {
      setMenu(next)
      setFilter("全部")
      setQuery("")
      scrollToListing()
      return
    }
    if (next === "badges") {
      setMenu("badges"); setQuery(""); pageContent.current?.scrollTo({top:0})
    } else if (next === "certification") {
      info(
        "能力认证 · 成长路线",
        "01 能力诊断：梳理岗位能力与证据缺口。\n02 学习补强：完成针对性的课程与练习。\n03 工作样本：提交能够体现真实判断的交付成果。\n04 模拟答辩：围绕问题、证据与取舍进行复盘。\n05 认证晋级：由导师评审后确认等级。当前为界面示例，不会自动变更你的正式等级。",
      )
    } else if (next === "lab") {
      info(
        "交付倒计时 · 风险升级演练",
        "你负责的项目距离交付仅剩 3 天，关键依赖延期且验收范围发生变化。\n练习目标：识别交付红线、制定备选方案，并说明何时升级风险。\n交付成果：风险清单、升级沟通稿和应急方案。\n这是合成工作样本，正式提交与导师验收接口尚未接入。",
      )
    } else {
      info(
        "设置",
        `当前身份：${identity}\n新手村的领取、保存草稿和提交记录已保存到当前账号。`,
      )
    }
  }
  const taskPool = practiceTasks.filter(t => menu !== "mine" || taskStatus(t.id) !== "available")
  const visibleTasks = filterDepartmentTasks(taskPool, taskDepartment, taskLevel, taskReview, query, taskBadgeType)
    .sort((a, b) =>
      sort === "duration"
        ? a.minutes - b.minutes
        : sort === "reward"
          ? b.experience - a.experience
          : 0,
    )
  const visibleCourses = academyCourses
    .filter(
      (c) =>
        (menu !== "saved" || favorites.includes(c.id)) &&
        (filter === "全部" || c.category === filter) &&
        `${c.title}${c.description}${c.domain}`.includes(query.trim()),
    )
    .sort((a, b) =>
      sort === "duration"
        ? a.minutes - b.minutes
        : sort === "popular"
          ? b.learners - a.learners
          : 0,
    )
  const openedTask = dialog?.type === "task" ? practiceTasks.find(t => t.id === dialog.task.id) ?? dialog.task : null
  const DialogSurface = openedTask ? JourneyDialogSurface : Fragment
  useEffect(() => {
    if (!villageEnabled || !practiceTasks.length) return
    const id = new URLSearchParams(window.location.search).get("task")
    if (id) {
      const selected = practiceTasks.find(t => t.id === id)
      if (selected) {
        const initial = window.setTimeout(() => { setDialog({type:"task", task:selected}); const url = new URL(window.location.href); url.searchParams.delete("task"); window.history.replaceState(null,"",url) }, 0)
        return () => window.clearTimeout(initial)
      }
    }
  }, [villageEnabled, practiceTasks])
  async function act(task:VillageTask, command:"claim"|"draft"|"submit") {
    const answer = practice[task.id]?.answer ?? task.answer
    if (command === "submit" && answer.trim().length < 40) { setNotice("请填写至少 40 个字的成果说明，可附作品链接。"); return }
    const result = await village.mutate(task, command, answer)
    if (result) {
      setPractice(previous => { const next = {...previous}; delete next[task.id]; return next })
      setNotice(command === "claim" ? "已领取任务" : command === "draft" ? "草稿已保存" : "已提交，等待审核")
    }
  }
  const title = module === "dashboard" ? "探索营" : moduleTitles[module]
  const updateTask = (id: string, patch: Partial<PracticeState>) => {
    if (!villageEnabled) { setNotice("暂未开放"); return }
    setPractice(previous => ({
      ...previous,
      [id]: { ...(previous[id] ?? { status: "available", answer: "" }), ...patch },
    }))
  }
  return (
    <ModuleBorderProvider decoration={decoration}>
      <div className="module-viewport design-viewport" data-screen={module}>
        <main
          className="module-hub"
          onClickCapture={event=>{
            const target=event.target as HTMLElement;
            if(menu!=="profile" && menu!=="map" && menu!=="knowledge" && module!=="dashboard" && !villageEnabled && !modulePagesEnabled && target.closest(".module-page-content") && target.closest("button")) {
              const button=target.closest("button");
              if(button?.hasAttribute("data-page-navigation"))return;
              if(button?.closest(".module-filterbar") || button?.closest(".module-filter-tabs"))return;
              event.preventDefault();event.stopPropagation();setNotice("暂未开放");
            }
          }}
          data-module={module}
          data-world-map={menu === "map" || undefined}
          style={{ zoom: canvasScale }}
        >
          <div className="module-space-background" aria-hidden="true">
            <img src="/assets/project29/home-4062/0ba79.webp" alt="" />
          </div>
          <ModuleSidebar
            module={module}
            onNavigate={onNavigate}
            onLogout={() => setAccountSwitchOpen(true)}
            onMenu={navigateMenu}
            activeMenu={menu}
            activeDecoration={activeNavigationDecoration}
            idleDecoration={idleNavigationDecoration}
            taskCount={explorationTaskCount}
          />
          <div className="module-main">
            <ModuleHeader
              module={module}
              menu={menu}
              identity={displayName || identity}
              query={query}
              onQuery={(value) => {
                setQuery(value)
                if (menu !== "profile" && menu !== "map" && menu !== "knowledge" && menu !== "badges" && menu !== "hall" && !(module === "academy" && menu === "saved")) setMenu("hall")
              }}
              onHome={() => { setMenu("hall"); setQuery(""); onNavigate("dashboard") }}
              onProfile={() => {
                if(menu!=="profile")setProfileReturn(menu)
                setMenu("profile");setQuery("");pageContent.current?.scrollTo({top:0})
              }}
            />
            <div className="module-map-host" data-active={menu === "map"} aria-hidden={menu !== "map"} inert={menu !== "map"}>
              <WorldMap active={active && menu === "map"} onViewTasks={module === "village" ? openMapDepartmentTasks : undefined} />
            </div>
            {module === "dashboard" && menu !== "profile" && menu !== "map" && menu !== "knowledge" ? (
              <div className="module-dashboard-content">{dashboardContent}</div>
            ) : (
              <div
                className="module-page-content"
                style={menu === "map" ? {display:"none"} : undefined}
                data-world-map={menu === "map" || undefined}
                ref={pageContent}
                tabIndex={0}
                role="region"
                aria-label={menu === "map" ? "世界地图内容" : `${title}内容，可滚动查看`}
              >
                {menu === "profile" ? (
                  <PersonalProfile name={displayName} onBack={()=>{setMenu(profileReturn);setQuery("")}} onAcademy={()=>{setMenu("saved");onNavigate("academy")}} />
                ) : menu === "map" ? (
                  null
                ) : menu === "knowledge" ? (
                  <KnowledgeLibrary key={module} module={module} query={query} onClearSearch={() => setQuery("")} />
                ) : module === "academy" && menu === "saved" ? (
                  <div className="favorite-knowledge-page">
                    <FavoriteKnowledge headingLevel="h1" courses={academyCourses} favoriteIds={favorites} query={query}
                      onToggle={() => setNotice("暂未开放")}
                      onOpen={course => setDialog({type:"course", course})}
                      onBrowse={() => navigateMenu("hall")} onClearSearch={() => setQuery("")} />
                  </div>
                ) : module === "village" && menu === "badges" ? (
                  <BadgeShop query={query} onTasks={() => {resetTaskFilters(); navigateMenu("hall")}} />
                ) : module !== "guild" && module !== "dashboard" ? (
                  <>
                    <div className="module-page-heading">
                      <div>
                        <h1>{title}</h1>
                        <p>
                          {module === "village"
                            ? "真正的大师，永远都怀着一颗学徒的心。"
                            : "在知识星海里，解锁你的下一种可能。"}
                        </p>
                      </div>
                      <div className="module-actions">
                        {module === "academy" && <button data-page-navigation className="module-secondary favorite-entry" onClick={() => navigateMenu("saved")}><ModuleIcon file="b5cc7" size={18} />我的收藏 <span className="favorite-entry-count">{favorites.length}</span></button>}
                        <button
                          className="module-secondary"
                          aria-disabled={(module === "village" && !villageEnabled) || undefined}
                          onClick={() =>
                            module === "village"
                              ? navigateMenu("hall")
                              : info(
                                  "学习记录",
                                  "学习记录暂未开放。",
                                )
                          }
                        >
                          <ModuleIcon file="42cb2" />
                          {module === "village" ? "已发布任务" : "学习记录"}
                        </button>
                        <button
                          className="module-secondary accent"
                          onClick={() =>
                            module === "village"
                              ? navigateMenu("mine")
                              : setDialog({ type: "share" })
                          }
                        >
                          <ModuleIcon file="d4a6c" />
                          {module === "village" ? "我的任务" : "分享我的发现"}
                        </button>
                      </div>
                    </div>
                    <div className="module-hero-grid">
                      <ModuleHero
                        module={module}
                        onContinue={() => {
                          if (module === "village") {
                            const first = accepted.find(task => ["active", "returned"].includes(task.status)) || practiceTasks[0]
                            if (first) setDialog({type:"task",task:first})
                            else { setNotice(village.loading ? "任务正在读取，请稍候。" : "暂时没有已发布的任务。"); scrollToListing() }
                          } else {
                            const course = academyCourses.find(c => !c.unavailable) || academyCourses[0]
                            if (course) setDialog({type:"course", course})
                            else info("AI 探索", "课程内容暂未开放。")
                          }
                        }}
                        title={
                          module === "village"
                            ? "从第一份任务，"
                            : "与 AI 共创，"
                        }
                        subtitle={
                          module === "village"
                            ? "走向独立交付。"
                            : "走向更大的自己。"
                        }
                        description={
                          module === "village"
                            ? "在真实问题中练习，把每一次尝试，变成看得见的成长。"
                            : "从一个灵感到一次实践，让每一份好奇，都成为成长路上的能量。"
                        }
                      />
                      <ModulePanel className="module-weekly">
                        <div className="module-row">
                          <h3>
                            {module === "village"
                              ? "我的实践进度"
                              : "本周探索任务"}
                          </h3>
                          <ModuleIcon
                            file={module === "village" ? "d7bdc" : "d7bdc"}
                            size={30}
                          />
                        </div>
                        <p className="module-weekly-count">
                          <strong>
                            {villageEnabled ? completed.length : "—"}
                          </strong>
                          <span>
                            / {villageEnabled ? accepted.length : "—"} {module === "village" ? "个任务" : "门课程"}
                          </span>
                        </p>
                        <div
                          className="module-progress-track"
                          role="progressbar"
                          aria-label={module === "village" ? "我的任务完成进度" : "本周进度"}
                          aria-valuemin={0}
                          aria-valuemax={Math.max(accepted.length, 1)}
                          aria-valuenow={villageEnabled ? completed.length : undefined}
                          aria-valuetext={villageEnabled ? undefined : "暂未开放"}
                        >
                          <i
                            style={{
                              width: `${((module === "village" ? completed.length : learned.length) / Math.max(accepted.length, 1)) * 100}%`,
                            }}
                          />
                        </div>
                        <div className="module-row module-small">
                          <span>
                            {module === "village"
                              ? "审核通过后完成"
                              : "每完成一门"}
                          </span>
                          <span className="module-cyan">
                            {villageEnabled ? "点亮能力" : "暂未开放"}
                          </span>
                        </div>
                        <blockquote>
                          {villageEnabled ? `已接取 ${accepted.length} 项 · 待审核 ${pending.length} 项。提交不等于完成，审核通过后才算完成。` : "暂未开放"}
                        </blockquote>
                      </ModulePanel>
                    </div>
                    <div ref={listing} className="module-listing">
                      <div className={`module-filterbar ${module === "village" ? "is-task-filter" : ""}`}>
                        {module === "village" ? <TaskClassifications tasks={taskPool} department={taskDepartment} level={taskLevel} review={taskReview} badgeType={taskBadgeType}
                          onDepartment={setTaskDepartment} onLevel={setTaskLevel} onReview={setTaskReview} onBadgeType={setTaskBadgeType} onReset={resetTaskFilters} /> :
                          <div className="module-tabs" role="group" aria-label="课程分类">{["全部", "管理员外链", "平台视频", "员工共建"].map(category => <button key={category} className={filter === category ? "is-active" : ""} aria-pressed={filter === category} onClick={() => setFilter(category)}>{category === "全部" ? "全部课程" : category}<span>{academyCourses.filter(c => category === "全部" || c.category === category).length}</span></button>)}</div>}
                        <label className="module-sort">
                          排序
                          <select
                            aria-label="排序方式"
                            value={sort}
                            onChange={(e) => setSort(e.target.value)}
                          >
                            <option value="recommended">推荐排序</option>
                            <option value="duration">用时最短</option>
                            {module === "village" ? (
                              <option value="reward">经验最多</option>
                            ) : (
                              <option value="popular">最多学习</option>
                            )}
                          </select>
                        </label>
                      </div>
                      <div className="module-list-caption">
                        <span>
                          {module === "village"
                            ? `${visibleTasks.length} 个任务 · ${
                                menu === "mine"
                                  ? "我的任务"
                                  : taskDepartmentName(taskDepartment)
                              }`
                            : `${visibleCourses.length} 门课程 · ${
                                menu === "saved"
                                  ? "我的收藏"
                                  : "首次完成获得探索经验，每门课程仅结算一次"
                              }`}
                        </span>
                        <span className="module-demo-label">
                          {villageEnabled ? "所有学员均可领取" : "暂未开放"}
                        </span>
                      </div>
                      {villageEnabled && village.loading && <p role="status">正在读取任务…</p>}
                      {villageEnabled && village.error && <p role="alert">{village.error} <button onClick={() => void village.refresh()}>重试</button></p>}
                      {module === "village" ? (
                        <div className="module-cards-grid">
                          {visibleTasks.map(task => (
                            <VillageTaskCard key={task.id} task={task} onOpen={() => setDialog({ type: "task", task })} />
                          ))}
                        </div>
                      ) : (
                        <div className="module-cards-grid">
                          {visibleCourses.map((course) => {
                            const index = academyCourses.indexOf(course)
                            return (
                              <ModulePanel
                                className="module-course-card"
                                key={course.id}
                              >
                                <div className="module-row">
                                  <span className="module-tag">
                                    <ModuleIcon
                                      file={
                                        [
                                          "0fa72",
                                          "7b4bc",
                                          "9aee4",
                                          "055ee",
                                          "1098f",
                                          "024ce",
                                        ][index]
                                      }
                                      size={13}
                                    />
                                    {course.category}
                                  </span>
                                  <KnowledgeSaveButton course={course} saved={favorites.includes(course.id)} onToggle={() => setNotice("暂未开放")} />
                                </div>
                                <button
                                  className="module-course-cover"
                                  onClick={() =>
                                    setDialog({ type: "course", course })
                                  }
                                  aria-label={`查看课程 ${course.title}`}
                                >
                                  <ModuleCourseArtwork index={index} />
                                  <span className="module-cover-label">
                                    {course.category === "管理员外链"
                                      ? "KNOWLEDGE PORTAL"
                                      : course.category === "平台视频"
                                        ? "ACADEMY CINEMA"
                                        : "CO-CREATION"}
                                  </span>
                                  <span className="module-cover-time">
                                    {course.minutes} 分钟
                                  </span>
                                </button>
                                <button
                                  className="module-card-title"
                                  onClick={() =>
                                    setDialog({ type: "course", course })
                                  }
                                >
                                  {course.title}
                                </button>
                                <p className="module-card-description">
                                  {course.description}
                                </p>
                                <div className="module-course-meta">
                                  <span>{course.level}</span>
                                  <span>{course.domain}</span>
                                  <span>{course.learners} 人学习</span>
                                </div>
                                <div className="module-course-reward">
                                  <span>
                                    {course.unavailable
                                      ? "资源状态"
                                      : learned.includes(course.id)
                                        ? "探索已完成"
                                        : "首次完成奖励"}
                                  </span>
                                  {course.unavailable ? (
                                    <ModuleStatus status="unavailable" />
                                  ) : learned.includes(course.id) ? (
                                    <ModuleStatus status="completed" />
                                  ) : (
                                    <strong>+50 XP</strong>
                                  )}
                                </div>
                                <div className="module-card-footer">
                                  <div className="module-author">
                                    <span className="module-avatar">
                                      {course.author[0]}
                                    </span>
                                    <span>
                                      {course.author}
                                      <small>
                                        {course.category === "员工共建"
                                          ? "课程分享人"
                                          : course.category}
                                      </small>
                                    </span>
                                  </div>
                                  <button
                                    onClick={() =>
                                      setDialog({ type: "course", course })
                                    }
                                  >
                                    {course.unavailable
                                      ? "查看状态"
                                      : learned.includes(course.id)
                                        ? "回看课程"
                                        : "查看课程"}{" "}
                                    →
                                  </button>
                                </div>
                              </ModulePanel>
                            )
                          })}
                        </div>
                      )}
                      {(module === "village"
                        ? !visibleTasks.length && !village.loading && !village.error
                        : !visibleCourses.length) && (
                        <ModulePanel className="module-empty">
                          <h3>
                            {villageEnabled ? (menu === "mine" ? "还没有接取任务" : taskDepartment !== "all" && taskLevel === "全部" && taskReview === "全部" && taskBadgeType === "全部" && !query.trim() ? "该部门暂无已发布任务" : !practiceTasks.length ? "暂无已发布任务" : "未找到匹配内容") : "暂未开放"}
                          </h3>
                          <p>{villageEnabled ? (!practiceTasks.length ? "管理员发布新手村任务后，会在这里显示。" : "试试其他分类或清空搜索词。") : "该板块暂未开放。"}</p>
                          <button
                            className="module-secondary"
                            onClick={() => {
                              setMenu("hall")
                              setFilter("全部")
                              resetTaskFilters()
                            }}
                          >
                            查看全部
                          </button>
                        </ModulePanel>
                      )}
                      {module === "academy" && shared.length > 0 && (
                        <ModulePanel className="module-shared-list">
                          <h3>我的共建提案 · 本次演示</h3>
                          {shared.map((item, i) => (
                            <div className="module-row" key={i}>
                              <span>{item.title}</span>
                              <ModuleStatus status="pending" />
                            </div>
                          ))}
                          <p>
                            提案尚未发送至后台，不会直接出现在公开课程列表。
                          </p>
                        </ModulePanel>
                      )}
                    </div>
                  </>
                ) : (
                  <GuildPage
                    guild={guild}
                    setGuild={setGuild}
                    identity={identity}
                    query={query}
                    info={info}
                    onLab={() => navigateMenu("lab")}
                    onCertification={() => navigateMenu("certification")}
                  />
                )}
                <footer className="module-footer">
                  <span>{title} · 每一步探索，都算数</span>
                  <button
                    onClick={() =>
                      info(
                        "配色与演示说明",
                        "新手村展示管理员发布的任务，所有学员均可领取。领取后可保存草稿、提交成果并查看审核反馈；退回的任务修改后可再次提交。",
                      )
                    }
                  >
                    功能说明 ↗
                  </button>
                </footer>
              </div>
            )}
          </div>
          {notice && (
            <div className="module-toast" role="status">
              {notice}
            </div>
          )}
          <dialog
            ref={modal}
            className={`module-dialog${openedTask ? " journey-dialog village-task-dialog" : ""}`}
            onCancel={() => setDialog(null)}
            onClick={(event) => {
              if (event.target === event.currentTarget) setDialog(null)
            }}
          >
            <DialogSurface>
            <div className="module-dialog-heading">
              <span className="module-eyebrow">
                {title} /{" "}
                {dialog?.type === "task"
                  ? "任务详情"
                  : dialog?.type === "course"
                    ? "课程详情"
                    : "成长空间"}
              </span>
              <button aria-label="关闭窗口" onClick={() => setDialog(null)}>
                关闭 ×
              </button>
            </div>
            {openedTask && (
              <>
                <div className="module-row"><div className="task-department-labels"><span className="module-tag">{openedTask.publishingDepartment || "部门待补充"}</span></div><ModuleStatus status={openedTask.status}/></div>
                <h2>{openedTask.title}</h2><p>{openedTask.description}</p>
                <div className="module-meta"><span>{openedTask.level}</span><span>{openedTask.minutes} 分钟</span><span>{openedTask.review}</span></div>
                <VillageTaskRewards task={openedTask} />
                <h3>学习材料</h3>
                <ul>{openedTask.materials.map((material,index) => <li key={index}>
                  {material.url ? <a className="module-cyan" href={material.url} target="_blank" rel="noopener noreferrer">{material.name} ↗</a> : <strong>{material.name}</strong>}
                  {material.text && <p style={{whiteSpace:"pre-wrap"}}>{material.text}</p>}
                </li>)}</ul>
                <section className="village-task-instructions">
                  <h3>任务要求</h3>
                  <ol className="village-task-instructions-body">{openedTask.requirements.map(r=><li key={r}>{r}</li>)}</ol>
                </section>
                <section className="village-task-instructions">
                  <h3>通关标准</h3>
                  <div className="village-task-instructions-body">{openedTask.criteria.map(c=><p key={c}>{c}</p>)}</div>
                </section>
                {openedTask.status === "available" && openedTask.unlockTaskPoints > 0 && <div className="module-demo-note">解锁需 {openedTask.unlockTaskPoints} 任务点，每人仅扣除一次。{village.wallet && `当前可用 ${village.wallet.taskPoints} 任务点。`}</div>}
                {openedTask.rubric.length > 0 && <><p>评分参考 · 及格线 {openedTask.passScore} 分，最终以人工审核为准。</p><ul>{openedTask.rubric.map(r=><li key={r.id}>{r.name} · {r.points} 分：{r.description}</li>)}</ul></>}
                {openedTask.feedback && <div className="module-demo-note"><strong>{openedTask.feedback.decision === "PASS" ? "审核通过" : "返回修改"}</strong><p style={{whiteSpace:"pre-wrap"}}>{openedTask.feedback.text}</p><time>{new Date(openedTask.feedback.at).toLocaleString("zh-CN")}</time></div>}
                {notice && <p role="status">{notice}</p>}
                {village.error && <p role="alert">{village.error}</p>}
                {openedTask.status === "available" ? <button className="module-primary module-claim-action" disabled={village.busy} onClick={()=>void act(openedTask,"claim")}>{village.busy ? "正在领取…" : "接取任务 →"}</button> : (
                  <form onSubmit={e=>{e.preventDefault();void act(openedTask,"submit")}}>
                    <label className="module-field">成果说明或作品链接
                      <textarea required minLength={40} maxLength={8000} rows={5}
                        disabled={village.busy || !["active","returned"].includes(openedTask.status)}
                        value={practice[openedTask.id]?.answer ?? openedTask.answer}
                        onChange={e=>updateTask(openedTask.id,{answer:e.target.value})}
                        placeholder="写下你的分析过程、结果与作品链接（至少 40 字）…"/>
                    </label>
                    {["active","returned"].includes(openedTask.status) && <button type="button" className="module-secondary" disabled={village.busy} onClick={()=>void act(openedTask,"draft")}>保存草稿</button>}
                    <button className="module-primary" disabled={village.busy || !["active","returned"].includes(openedTask.status)}>
                      {village.busy ? "正在保存…" : openedTask.status === "pending" ? "已提交，等待审核" : openedTask.status === "completed" ? "已完成" : openedTask.status === "returned" ? "重新提交审核" : "提交审核"}
                    </button>
                  </form>
                )}
              </>
            )}
            {dialog?.type === "course" && (
              <>
                <ModuleCourseArtwork
                  index={academyCourses.indexOf(dialog.course)}
                />
                <span className="module-tag">{dialog.course.category}</span>
                <h2>{dialog.course.title}</h2>
                <p>{dialog.course.description}</p>
                <div className="module-meta">
                  <span>{dialog.course.minutes} 分钟</span>
                  <span>{dialog.course.level}</span>
                  <span>{dialog.course.domain}</span>
                </div>
                {dialog.course.unavailable ? (
                  <div className="module-demo-note">
                    <ModuleStatus status="unavailable" />
                    <p>
                      此课程展示外部链接失效状态。请稍后查看更新，或选择其他课程；不会打开虚构链接或产生学习奖励。
                    </p>
                  </div>
                ) : (
                  <>
                    <h3>你将学到</h3>
                    <ol>
                      <li>把目标拆解为明确的输入、步骤和可检验的输出。</li>
                      <li>用 AI 完成一轮草稿，再核对事实、来源和表达。</li>
                      <li>将方法应用到自己的岗位场景，整理可复用的模板。</li>
                    </ol>
                    <div className="module-demo-note">
                      {dialog.course.category === "平台视频"
                        ? "设计稿未提供视频文件，本页展示课程介绍，不模拟视频播放。"
                        : "设计稿未提供真实课程地址，本页展示课程介绍，不跳转到虚构资料。"}{" "}
                      学习进度功能暂未开放。
                    </div>
                    <button
                      className="module-primary"
                      disabled={learned.includes(dialog.course.id)}
                      onClick={() => setNotice("暂未开放")}
                    >
                      暂未开放
                    </button>
                  </>
                )}
              </>
            )}
            {dialog?.type === "info" && (
              <>
                <h2>{dialog.title}</h2>
                <p className="module-info-body">{dialog.body}</p>
              </>
            )}
            {dialog && !openedTask && notice && <p role="status">{notice}</p>}
            {dialog?.type === "share" && (
              <>
                <h2>分享我的发现</h2>
                <p>分享一份可复用的方法或资源，让好经验在学院流动。</p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    setNotice("暂未开放")
                  }}
                >
                  <label className="module-field">
                    课程名称
                    <input
                      name="title"
                      required
                      maxLength={60}
                      placeholder="给你的方法起一个清晰的名字"
                    />
                  </label>
                  <label className="module-field">
                    资源链接
                    <input
                      name="url"
                      type="url"
                      required
                      placeholder="https://…"
                    />
                  </label>
                  <label className="module-field">
                    推荐理由
                    <textarea
                      name="reason"
                      rows={4}
                      required
                      minLength={10}
                      placeholder="它解决了什么问题？适合哪些同学？"
                    />
                  </label>
                  <div className="module-demo-note">
                    分享功能暂未开放，当前可查看表单。
                  </div>
                  <button type="button" className="module-primary" onClick={() => setNotice("暂未开放")}>暂未开放</button>
                </form>
              </>
            )}
            </DialogSurface>
          </dialog>
          <AccountSwitchDialog open={accountSwitchOpen} onClose={()=>setAccountSwitchOpen(false)} />
          <WelcomeNameDialog open={nicknameRequired} decoration={decoration} onSave={saveLearnerNickname} />

        </main>
      </div>
    </ModuleBorderProvider>
  )
}

function GuildPage({
  guild,
  setGuild,
  identity,
  query,
  info,
  onLab,
  onCertification,
}: {
  guild: string
  setGuild: (guild: string) => void
  identity: string
  query: string
  info: (title: string, body: string) => void
  onLab: () => void
  onCertification: () => void
}) {
  const paths = [
    {
      title: "能力地图",
      description: "看见差距，找到有针对性的补强方向。",
      image: "90975.webp",
      icon: "9aa97",
    },
    {
      title: "认证竞技场",
      description: "交付作品、接受 Panel 评审，证明岗位能力。",
      image: "04543.webp",
      icon: "a6862",
    },
    {
      title: "公会赛季",
      description: "与同行组队，把个人经验变成共同资产。",
      image: "96be2.webp",
      icon: "ce04e",
    },
  ].filter((p) => `${p.title}${p.description}`.includes(query.trim()))
  return (
    <>
      <div className="module-guild-picker">
        <span>当前岗位公会</span>
        <select
          aria-label="当前岗位公会"
          value={guild}
          onChange={(e) => setGuild(e.target.value)}
        >
          <option>PM</option>
          <option>技术开发</option>
          <option>数据交付</option>
        </select>
        <span>岗位公会</span>
        <span className="module-demo-label">暂未开放</span>
      </div>
      <ModuleHero
        module="guild"
        onContinue={onCertification}
        onIdentity={() =>
          info(
            "我的公会身份",
            "暂未开放",
          )
        }
        title={`${guild} 岗位公会`}
        subtitle="让每一次交付，成为专业的证明。"
        description="围绕需求、质量、风险与协同，让每一次交付留下可验证的专业证据。"
      />
      <div className="module-guild-grid">
        <div>
          <button
            className="module-announcement"
            onClick={() =>
              info(
                "公会公告 · 演示",
                "本期主题：用一份好作品，让同行看见你的专业。\n1. 带着一个真实工作问题参与能力诊断。\n2. 选一门补强课程，并整理实践记录。\n3. 提交工作样本，由导师进行评审。\n活动时间、报名和审核均待正式配置。",
              )
            }
          >
            <ModuleIcon pack="guild" file="ca8b1" />
            <span>公会公告</span>
            <span>用一份好作品，让同行看见你的专业。</span>
            <span>查看公告 →</span>
          </button>
          <ModulePanel className="module-guild-journey">
            <div className="module-row">
              <div>
                <small className="module-eyebrow">YOUR GUILD JOURNEY</small>
                <h3>我的公会进阶</h3>
              </div>
              <button onClick={onCertification}>完整路线 →</button>
            </div>
            <div className="module-guild-level">
              <span className="module-level-shield">
                <ModuleIcon pack="guild" file="8ddc0" size={24} />
                <small>—</small>
              </span>
              <div>
                <h3>暂未开放</h3>
                <p>公会进阶暂未开放。</p>
              </div>
              <strong>
                —<small>%</small>
              </strong>
            </div>
            <div className="module-progress-track">
              <i style={{ width: "0%" }} />
            </div>
            <div className="module-guild-steps">
              {["能力诊断", "学习补强", "工作样本", "模拟答辩", "认证晋级"].map(
                (step, index) => (
                  <button key={step} onClick={onCertification}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    {step}
                  </button>
                ),
              )}
            </div>
            <div className="module-lab-recommendation">
              <img src="/assets/project29/dashboard-2047/07842.webp" alt="工作样本文档" />
              <div>
                <small className="module-eyebrow">推荐补强 / 风险管理</small>
                <h3>交付倒计时 · 风险升级演练</h3>
                <p>识别交付红线，练习升级判断与备选方案。</p>
                <span className="module-tag">合成工作样本</span>{" "}
                <span className="module-tag">导师人工验收</span>
              </div>
              <button className="module-secondary" onClick={onLab}>
                进入实验室 →
              </button>
            </div>
          </ModulePanel>
          <div className="module-section-heading">
            <small className="module-eyebrow">GROW WITH YOUR GUILD</small>
            <h3>在公会里，找到下一次突破</h3>
          </div>
          <div className="module-guild-paths">
            {paths.map((path) => (
              <ModulePanel className="module-guild-path" key={path.title}>
                <button
                  onClick={() =>
                    info(
                      path.title,
                      `${path.description}\n${
                        path.title === "能力地图"
                          ? "需求分析、交付质量、风险控制、跨团队协作，是当前的四个能力维度。下一步可以进入新手村，选择对应练习。"
                          : path.title === "认证竞技场"
                            ? "准备工作样本、个人复盘和关键证据，按照能力标准参加导师评审。正式报名与评审尚未接入。"
                            : "本季主题：让好经验，在公会里流动。示例活动包括模板共建、案例复盘和团队挑战；正式报名尚未开放。"
                      }`,
                    )
                  }
                >
                  <img
                    className="module-path-image"
                    src={sharedAsset(`/assets/project29/modules/guild/${path.image}`)}
                    alt=""
                  />
                  <div>
                    <h3>
                      <ModuleIcon pack="guild" file={path.icon} />
                      {path.title}
                      <span>↗</span>
                    </h3>
                    <p>{path.description}</p>
                  </div>
                </button>
              </ModulePanel>
            ))}
          </div>
          {!paths.length && (
            <p className="module-empty">没有匹配的公会入口，请清空搜索词。</p>
          )}
        </div>
        <aside className="module-guild-aside">
          <ModulePanel className="module-identity-card">
            <div className="module-row">
              <h3>我的公会身份</h3>
              <span className="module-demo-label">暂未开放</span>
            </div>
            <div className="module-author">
              <span className="module-avatar">学</span>
              <span>
                学员 {identity}
                <small>{guild} 岗位公会 · 暂未开放</small>
              </span>
              <span className="module-tag">—</span>
            </div>
            <div className="module-identity-stats">
              <div>
                <strong>—</strong>
                <small>已验收作品</small>
              </div>
              <div>
                <strong>—</strong>
                <small>公会贡献</small>
              </div>
            </div>
            <small>公会 Owner</small>
            <p>暂未开放</p>
          </ModulePanel>
          <ModulePanel>
            <div className="module-row">
              <h3>你的公会导师</h3>
              <button
                onClick={() =>
                  info(
                    "公会导师",
                    "导师名单暂未开放。",
                  )
                }
              >
                全部 →
              </button>
            </div>
            <div className="module-author">
              <span className="module-avatar outline">—</span>
              <span>
                —<small>暂未开放</small>
              </span>
            </div>
            <p>“把你面临的真实问题带来，我们一起把下一步想清楚。”</p>
            <button
              className="module-secondary module-full-width"
              onClick={() =>
                info(
                  "预约导师交流",
                  "建议交流前准备：\n1. 当前遇到的真实问题。\n2. 已尝试的方法和现有证据。\n3. 希望获得的具体帮助。\n设计稿未提供导师日程或联系方式，目前不能发起真实预约。",
                )
              }
            >
              <ModuleIcon pack="guild" file="674d5" size={16} />
              预约导师交流
            </button>
          </ModulePanel>
          <ModulePanel>
            <div className="module-row">
              <h3>同行正在发生</h3>
              <ModuleIcon pack="guild" file="0c0f8" />
            </div>
            <p className="module-muted" role="status">暂未开放</p>
            {([] as string[][]).map(([letter, heading, text]) => (
              <div className="module-peer" key={letter}>
                <span className="module-avatar">{letter}</span>
                <div>
                  <span>{heading}</span>
                  <small>{text}</small>
                </div>
              </div>
            ))}
          </ModulePanel>
          <ModulePanel className="module-season">
            <small className="module-eyebrow">公会赛季 · 暂未开放</small>
            <h3>让好经验，在公会里流动。</h3>
            <button
              onClick={() =>
                info(
                  "秋季共创 · 演示活动",
                  "主题：分享一次真实交付中的方法与复盘。\n成果：一份可复用的模板或案例。\n示例周期：10.01—11.30。正式活动尚未配置，不会产生报名记录。",
                )
              }
            >
              暂未开放 <span>→</span>
            </button>
          </ModulePanel>
        </aside>
      </div>
    </>
  )
}
