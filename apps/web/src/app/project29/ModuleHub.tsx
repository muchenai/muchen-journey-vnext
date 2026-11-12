import { BadgeShop, type BadgeTab } from "./BadgeShop"
import { DashboardSearchProvider } from "./dashboardSearch"
import { TaskClassifications } from "./TaskClassifications"
import { filterDepartmentTasks, taskDepartmentName, type TaskDepartmentFilter } from "./taskDepartments"
import { filterVillageTaskStatus, sortVillageTasks, type VillageTaskStatusFilter } from "./villageTaskList"
import { useVillageTasks, isVillageTaskClaimed, type VillageTask, type VillageTaskCommand } from "./useVillageTasks"
import { VillageTaskForm } from "./VillageTaskForm"
import { VillageTaskMaterials } from "./VillageTaskMaterials"
import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { sharedAsset } from "./sharedAsset"
import type { PreviewIdentity } from "./previewStorage"
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
import { AcademyLearning } from "./AcademyLearning"
import { DeliveryLab } from "./DeliveryLab"
import { createDeliveryLabSession } from "./deliveryLabModel"
import { GuildGrowthPage } from "./GuildGrowthPage"
import type { GuildView } from "./guildGrowthModel"
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
  const [menu, setMenu] = useState("hall")
  const [profileReturn, setProfileReturn] = useState("hall")
  const [badgeEntryTab, setBadgeEntryTab] = useState<BadgeTab>("shop")
  const [badgeEntryVersion, setBadgeEntryVersion] = useState(0)
  const [accountSwitchOpen, setAccountSwitchOpen] = useState(false)
  const displayName = identity
  const [taskDepartment, setTaskDepartment] = useState<TaskDepartmentFilter>("all")
  const [taskLevel, setTaskLevel] = useState("全部")
  const [taskReview, setTaskReview] = useState("全部")
  const [taskBadgeType, setTaskBadgeType] = useState("全部")
  const [taskStatusFilter, setTaskStatusFilter] = useState<VillageTaskStatusFilter>("all")
  const resetTaskFilters = () => {setTaskDepartment("all"); setTaskLevel("全部"); setTaskReview("全部"); setTaskBadgeType("全部"); setTaskStatusFilter("all"); setQuery("")}
  const [filter, setFilter] = useState("全部")
  const [search, setSearch] = useState({ module, value: "" })
  const query = search.module === module ? search.value : ""
  const setQuery = useCallback((value: string) => setSearch({ module, value }), [module])
  const [sort, setSort] = useState("recommended")
  const [practice, setPractice] = useState<Record<string, PracticeState>>({})
  const [favorites] = useState<string[]>([])
  const [learned] = useState<string[]>([])
  const [dialog, setDialog] = useState<DialogState>(null)
  const [notice, setNotice] = useState("")
  const [savedDraftTaskId, setSavedDraftTaskId] = useState<string | null>(null)
  const [deliveryLab, setDeliveryLab] = useState(createDeliveryLabSession)
  const [shared] = useState<{ title: string; url: string }[]>([])
  const modal = useRef<HTMLDialogElement>(null)
  const listing = useRef<HTMLDivElement>(null)
  const pageContent = useRef<HTMLDivElement>(null)
  const pendingMapTaskScroll = useRef(false)
  const pendingMapTaskDepartment = useRef<TaskDepartmentFilter | null>(null)
  const pendingAcademyFavorites = useRef(false)
  const pendingVillageMenu = useRef<"hall" | "badges" | null>(null)
  const openMapDepartmentTasks = useCallback((department: TaskDepartmentFilter) => {
    if (module !== "village") {
      if (module !== "academy" && module !== "guild") return
      pendingMapTaskDepartment.current = department
      pendingVillageMenu.current = "hall"
      onNavigate("village")
      return
    }
    setMenu("hall")
    setTaskDepartment(department)
    setTaskLevel("全部")
    setTaskReview("全部")
    setTaskBadgeType("全部")
    setTaskStatusFilter("all")
    setQuery("")
    setFilter("全部")
    setSort("recommended")
    setDialog(null)
    setNotice("")
    pendingMapTaskScroll.current = true
  }, [module, onNavigate, setQuery, setFilter])
  useLayoutEffect(() => {
    if (module !== "village" || menu !== "hall" || !pendingMapTaskScroll.current || !listing.current || !pageContent.current) return
    pendingMapTaskScroll.current = false
    pageContent.current.scrollTo({
      top: listing.current.offsetTop - pageContent.current.offsetTop - 24,
      behavior: "auto",
    })
  }, [module, menu, taskDepartment])
  useEffect(() => {
    const initial = window.setTimeout(() => {
      const mapDepartment = module === "village" ? pendingMapTaskDepartment.current : null
      pendingMapTaskDepartment.current = null
      setMenu(module === "village" && pendingVillageMenu.current ? pendingVillageMenu.current : module === "academy" && pendingAcademyFavorites.current ? "saved" : "hall")
      if (!(module === "village" && pendingVillageMenu.current === "badges")) setBadgeEntryTab("shop")
      pendingVillageMenu.current = null
      pendingAcademyFavorites.current = false
      resetTaskFilters()
      if (mapDepartment) setTaskDepartment(mapDepartment)
      pendingMapTaskScroll.current = mapDepartment !== null
      setFilter("全部")
      setQuery("")
      setSort("recommended")
      setDialog(null)
      setNotice("")
      if (!mapDepartment) pageContent.current?.scrollTo({ top: 0 })
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
  const accepted = practiceTasks.filter(isVillageTaskClaimed)
  const pending = accepted.filter((t) => taskStatus(t.id) === "pending")
  const completed = accepted.filter((t) => taskStatus(t.id) === "completed")
  const info = (title: string, body: string) => {
    if (module === "guild" || villageEnabled || modulePagesEnabled) setDialog({ type: "info", title, body })
    else setNotice("暂未开放")
  }
  const scrollToListing = () => {
    if (!listing.current || !pageContent.current) return
    pageContent.current.scrollTo({
      top: listing.current.offsetTop - pageContent.current.offsetTop - 24,
      behavior: "smooth",
    })
  }
  function openAcademy(next: "hall" | "saved") {
    pendingAcademyFavorites.current = module !== "academy" && next === "saved"
    setMenu(next)
    setFilter("全部")
    setQuery("")
    pageContent.current?.scrollTo({ top: 0 })
    onNavigate("academy")
  }
  function openGuildVillage(next: "hall" | "badges", badgeTab: BadgeTab = "catalog") {
    pendingVillageMenu.current = module === "village" ? null : next
    setBadgeEntryTab(badgeTab)
    if (next === "badges") setBadgeEntryVersion(version => version + 1)
    resetTaskFilters()
    setDialog(null)
    setNotice("")
    if (module === "village") setMenu(next)
    pageContent.current?.scrollTo({ top: 0 })
    onNavigate("village")
  }
  function navigateMenu(next: string) {
    if (module === "guild" && ["hall", "lab", "certification", "capability-map", "arena"].includes(next)) {
      setMenu(next)
      setQuery("")
      pageContent.current?.scrollTo({ top: 0 })
      return
    }
    if (next === "map" || next === "knowledge") {
      setMenu(next)
      setQuery("")
      pageContent.current?.scrollTo({ top: 0 })
      return
    }
    if (module === "dashboard") {
      if (next === "hall" || next === "tasks") {
        setMenu("hall")
        setQuery("")
      }
      onExplorationMenu(next)
      return
    }
    if (["hall", "mine", "saved"].includes(next)) {
      setMenu(next)
      setTaskStatusFilter("all")
      setFilter("全部")
      setQuery("")
      scrollToListing()
      return
    }
    if (next === "badges") {
      setBadgeEntryTab("shop"); setBadgeEntryVersion(version => version + 1); setMenu("badges"); setQuery(""); pageContent.current?.scrollTo({top:0})

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
  const taskPool = practiceTasks.filter(t => menu !== "mine" || isVillageTaskClaimed(t))
  const visibleTasks = sortVillageTasks(filterVillageTaskStatus(
    filterDepartmentTasks(taskPool, taskDepartment, taskLevel, taskReview, query, taskBadgeType),
    menu === "mine" ? taskStatusFilter : "all",
  ), sort)
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
  const DialogSurface = openedTask || module === "guild" ? JourneyDialogSurface : Fragment
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
  async function act(task:VillageTask, command:VillageTaskCommand) {
    const answer = practice[task.id]?.answer ?? task.answer
    if (command === "cancel" && task.status !== "active") return false
    if (command === "submit" && answer.trim().length < 40) { setNotice("请填写至少 40 个字的成果说明，可附作品链接。"); return false }
    setNotice("")
    setSavedDraftTaskId(null)
    const result = await village.mutate(task, command, answer)
    if (result) {
      setPractice(previous => { const next = {...previous}; delete next[task.id]; return next })
      if (command === "draft") setSavedDraftTaskId(task.id)
      setNotice(command === "claim" ? "已领取任务" : command === "cancel" ? result.status === "available" ? "已取消接取，任务恢复为可接取。已保存的草稿已保留。" : result.status === "unavailable" ? "已取消接取；该任务当前不可重新接取。已保存的草稿已保留。" : "取消请求已处理，任务状态随后发生了更新，请以当前页面显示为准。" : command === "draft" ? "草稿保存成功" : "已提交，等待审核")
    }
    return !!result
  }
  const title = module === "dashboard" ? "探索营" : moduleTitles[module]
  const updateTask = (id: string, patch: Partial<PracticeState>) => {
    if (!villageEnabled) { setNotice("暂未开放"); return }
    if (savedDraftTaskId === id) { setSavedDraftTaskId(null); setNotice("") }
    setPractice(previous => ({
      ...previous,
      [id]: { ...(previous[id] ?? { status: "available", answer: "" }), ...patch },
    }))
  }
  return (
    <ModuleBorderProvider decoration={decoration}>
      <div className="module-viewport design-viewport" data-screen={module}>
        <main
          className="module-hub journey-scaled-canvas"
          onClickCapture={event=>{
            const target=event.target as HTMLElement;
            if(menu!=="profile" && menu!=="map" && menu!=="knowledge" && module!=="dashboard" && module!=="academy" && module!=="guild" && !villageEnabled && !modulePagesEnabled && target.closest(".module-page-content") && target.closest("button")) {
              const button=target.closest("button");
              if(button?.hasAttribute("data-page-navigation"))return;
              if(button?.closest(".module-filterbar") || button?.closest(".module-filter-tabs"))return;
              event.preventDefault();event.stopPropagation();setNotice("暂未开放");
            }
          }}
          data-module={module}
          data-world-map={menu === "map" || undefined}
        >
          <div className="module-space-background" aria-hidden="true">
            <img src="/assets/project29/home-4062/0ba79.webp" alt="" />
          </div>
          <ModuleSidebar
            module={module}
            onNavigate={onNavigate}
            onLogout={() => setAccountSwitchOpen(true)}
            onMenu={navigateMenu}
            activeMenu={module === "guild" && menu === "arena" ? "hall" : module === "guild" && menu === "capability-map" ? "certification" : menu}
            activeDecoration={activeNavigationDecoration}
            idleDecoration={idleNavigationDecoration}
            taskCount={explorationTaskCount}
          />
          <div className="module-main">
            <ModuleHeader
              active={active}
              module={module}
              menu={menu}
              identity={displayName || identity}
              query={query}
              onQuery={(value) => {
                setQuery(value)
                if (menu !== "profile" && menu !== "map" && menu !== "knowledge" && menu !== "badges" && menu !== "hall" && !(module === "guild" && ["lab", "certification", "capability-map", "arena"].includes(menu)) && !(module === "academy" && menu === "saved")) setMenu("hall")
              }}
              onHome={() => { setMenu("hall"); setQuery(""); onNavigate("dashboard") }}
              onProfile={() => {
                if(menu!=="profile")setProfileReturn(menu)
                setMenu("profile");setQuery("");pageContent.current?.scrollTo({top:0})
              }}
            />
            <div className="module-map-host" data-active={menu === "map"} aria-hidden={menu !== "map"} inert={menu !== "map"}>
              <WorldMap contextKey={module} active={active && menu === "map"} onViewTasks={module === "village" || module === "academy" || module === "guild" ? openMapDepartmentTasks : undefined} />
            </div>
            {module === "dashboard" && menu !== "profile" && menu !== "map" && menu !== "knowledge" ? (
              <div className="module-dashboard-content">
                <DashboardSearchProvider query={query} onClearSearch={() => setQuery("")}>
                  {dashboardContent}
                </DashboardSearchProvider>
              </div>
            ) : (
              <div
                className="module-page-content"
                style={menu === "map" ? {display:"none"} : undefined}
                data-world-map={menu === "map" || undefined}
                data-delivery-lab={module === "guild" && menu === "lab"}
                data-guild-growth={module === "guild" && ["hall", "certification", "capability-map", "arena"].includes(menu)}
                ref={pageContent}
                tabIndex={0}
                role="region"
                aria-label={menu === "map" ? "世界地图内容" : `${title}内容，可滚动查看`}
              >
                {module === "guild" && menu === "lab" ? (
                  <DeliveryLab identity={identity} session={deliveryLab} onChange={setDeliveryLab} query={query} onClearSearch={() => setQuery("")} />
                ) : menu === "profile" ? (
                  <PersonalProfile name={displayName} onBack={()=>{setMenu(profileReturn);setQuery("")}} onAcademy={()=>openAcademy("hall")} onAcademyFavorites={()=>openAcademy("saved")} onBadgeShop={()=>openGuildVillage("badges", "shop")} onBadgeCatalog={()=>openGuildVillage("badges", "catalog")} onBadgeOwned={()=>openGuildVillage("badges", "owned")} />
                ) : menu === "map" ? (
                  null
                ) : menu === "knowledge" ? (
                  <KnowledgeLibrary key={module} module={module} query={query} onClearSearch={() => setQuery("")} />
                ) : ["academy"].includes(module) ? (
                  <AcademyLearning active={active} savedOnly={menu === "saved"} query={query} onSaved={saved => { setMenu(saved ? "saved" : "hall"); setQuery("") }} onClearSearch={() => setQuery("")} />
                ) : module === "academy" && menu === "saved" ? (
                  <div className="favorite-knowledge-page">
                    <FavoriteKnowledge headingLevel="h1" courses={academyCourses} favoriteIds={favorites} query={query}
                      onToggle={() => setNotice("暂未开放")}
                      onOpen={course => setDialog({type:"course", course})}
                      onBrowse={() => navigateMenu("hall")} onClearSearch={() => setQuery("")} />
                  </div>
                ) : module === "village" && menu === "badges" ? (
                  <BadgeShop key={badgeEntryVersion} initialTab={badgeEntryTab} query={query} onTasks={() => {resetTaskFilters(); navigateMenu("hall")}} />
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
                          status={menu === "mine" ? taskStatusFilter : undefined} onStatus={setTaskStatusFilter} visibleCount={visibleTasks.length}
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
                            {villageEnabled ? (menu === "mine" ? accepted.length ? "未找到符合筛选的任务" : "还没有接取任务" : taskDepartment !== "all" && taskLevel === "全部" && taskReview === "全部" && taskBadgeType === "全部" && !query.trim() ? "该部门暂无已发布任务" : !practiceTasks.length ? "暂无已发布任务" : "未找到匹配内容") : "暂未开放"}
                          </h3>
                          <p>{villageEnabled ? (!practiceTasks.length ? "管理员发布新手村任务后，会在这里显示。" : menu === "mine" && accepted.length ? "试试其他状态或清空筛选条件。" : "试试其他分类或清空搜索词。") : "该板块暂未开放。"}</p>
                          <button
                            className="module-secondary"
                            onClick={() => {
                              if (menu !== "mine" || !accepted.length) setMenu("hall")
                              setFilter("全部")
                              resetTaskFilters()
                            }}
                          >
                            {menu === "mine" && accepted.length ? "清空筛选" : "查看全部"}
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
                  <GuildGrowthPage
                    key={identity}
                    view={(["hall", "certification", "capability-map", "arena"].includes(menu) ? menu : "hall") as GuildView}
                    identity={identity}
                    active={active}
                    query={query}
                    onView={navigateMenu}
                    onBadges={() => openGuildVillage("badges")}
                    onAcademy={() => openAcademy("hall")}
                    onLab={() => navigateMenu("lab")}
                  />
                )}
                <footer className="module-footer">
                  <span>{title} · 每一步探索，都算数</span>
                  <button
                    onClick={() =>
                      info(
                        module === "guild" ? "配色与演示说明" : "功能说明",
                        module === "guild"
                          ? "三个新板块统一使用 19 个语义基础色，标签沿用探索营的状态规范：进行中为青色，待审核为金色，已完成为绿色，待解锁为灰蓝。插画与照片保留设计原貌，不计入界面配色。新示例操作仅在本次会话中体验；原有探索营和发布任务记录不受影响。"
                          : "新手村展示管理员发布的任务，所有学员均可领取。领取后可保存草稿、提交成果并查看审核反馈；退回的任务修改后可再次提交。",
                      )
                    }
                  >
                    {module === "guild" ? "设计与演示说明 ↗" : "功能说明 ↗"}
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
            className={`module-dialog${openedTask || module === "guild" ? " journey-dialog" : ""}${openedTask ? " village-task-dialog" : ""}`}
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
                <VillageTaskMaterials task={openedTask} />
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
                {notice && notice !== "草稿保存成功" && <p role="status">{notice}</p>}
                {village.error && <p role="alert">{village.error}</p>}
                {openedTask.status === "available" ? <button className="module-primary module-claim-action" disabled={village.busy} onClick={()=>void act(openedTask,"claim")}>{village.busy ? "正在领取…" : "接取任务 →"}</button> : (
                  <VillageTaskForm key={`${openedTask.id}:${openedTask.assignmentId}:${openedTask.revision}:${openedTask.status}`} task={openedTask}
                    busy={village.busy} answer={practice[openedTask.id]?.answer ?? openedTask.answer}
                    savedMessage={savedDraftTaskId === openedTask.id && notice === "草稿保存成功" ? notice : ""}
                    onAnswer={answer=>updateTask(openedTask.id,{answer})} onAction={command=>act(openedTask,command)} />
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
          <WelcomeNameDialog open={active && nicknameRequired} decoration={decoration} onSave={saveLearnerNickname} />

        </main>
      </div>
    </ModuleBorderProvider>
  )
}
