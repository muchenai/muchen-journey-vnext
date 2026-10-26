import { useEffect, useRef, useState, type ReactNode } from "react"
import { sharedAsset } from "./sharedAsset"
import type { PreviewIdentity } from "./previewStorage"
import { useCanvasScale } from "./useCanvasScale"
import { WelcomeNameDialog } from "./WelcomeNameDialog"
import { saveLearnerNickname } from "../actions"
import {

  moduleTitles,

  type AcademyCourse,
  type ModuleName,
  type PracticeTask,
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
import { ModuleCourseArtwork } from "./ModuleCourseArtwork"
import "./moduleHub.css"

const academyCourses: AcademyCourse[] = [];
const practiceTasks: PracticeTask[] = [];

type PracticeState = { status: ModuleStatusName; answer: string }
type DialogState = { type: "task"; task: PracticeTask } | {
  type: "course"
  course: AcademyCourse
} | { type: "info"; title: string; body: string } | { type: "share" } | null

export function ModuleHub({
  module,
  identity,
  onNavigate,
  onLogout,
  decoration,
  activeNavigationDecoration,
  idleNavigationDecoration,
  dashboardContent,
  onExplorationMenu,
  explorationTaskCount = 0,
  nicknameRequired = false,
}: {
  module: ModuleDestination
  identity: PreviewIdentity
  onNavigate: (destination: ModuleDestination) => void
  onLogout: () => void
  decoration: ReactNode
  activeNavigationDecoration: ReactNode
  idleNavigationDecoration: ReactNode
  dashboardContent?: ReactNode
  onExplorationMenu: (menu: string) => void
  explorationTaskCount?: number
  nicknameRequired?: boolean
}) {
  const canvasScale = useCanvasScale()
  const [menu, setMenu] = useState("hall")
  const [previousModule, setPreviousModule] = useState(module)
  const displayName = identity
  const [filter, setFilter] = useState("全部")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState("recommended")
  const [practice, setPractice] = useState<Record<string, PracticeState>>({})
  const [favorites, setFavorites] = useState<string[]>([])
  const [learned, setLearned] = useState<string[]>([])
  const [dialog, setDialog] = useState<DialogState>(null)
  const [notice, setNotice] = useState("")
  const [guild, setGuild] = useState("PM")
  const [shared, setShared] = useState<{ title: string; url: string }[]>([])
  const modal = useRef<HTMLDialogElement>(null)
  const listing = useRef<HTMLDivElement>(null)
  const pageContent = useRef<HTMLDivElement>(null)
  if (previousModule !== module) {
    setPreviousModule(module)
    setMenu("hall")
    setFilter("全部")
    setQuery("")
    setSort("recommended")
    setDialog(null)
    setNotice("")
  }
  useEffect(() => {
    pageContent.current?.scrollTo({ top: 0 })
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
    practice[id]?.status || "available"
  const accepted = practiceTasks.filter((t) => taskStatus(t.id) !== "available")
  const pending = accepted.filter((t) => taskStatus(t.id) === "pending")
  const completed = accepted.filter((t) => taskStatus(t.id) === "completed")
  const info = (_title: string, _body: string) => setNotice("暂未开放")
  const scrollToListing = () => {
    if (!listing.current || !pageContent.current) return
    pageContent.current.scrollTo({
      top: listing.current.offsetTop - pageContent.current.offsetTop - 24,
      behavior: "smooth",
    })
  }
  function navigateMenu(next: string) {
    if (module === "dashboard") {
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
      info(
        "我的徽章",
        `新手村覆盖产品开发、技术开发、数据交付、PMO、AI 评测和质量检测等能力方向。示例任务提交后为待审核，审核通过才获得经验和徽章点。当前已接取 ${accepted.length} 项，待审核 ${pending.length} 项。`,
      )
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
    } else if (next === "map") {
      info(
        "成长地图",
        "探索营：建立基础认知。\n新手村：用任务完成第一次实践。\nAI 学院：学习方法与工具，提升工作效率。\n交付线工会：积累工作样本，迈向专业认证。\n可通过左侧板块入口继续探索。",
      )
    } else if (next === "knowledge") {
      info(
        "知识库",
        "任务模板：访谈洞察卡、风险清单、数据质量报告、测试用例。\n学习方法：角色—任务—背景—输出格式，先明确目标，再核对证据。\n示例资料未配置外部链接，可先在 AI 学院查看课程介绍。",
      )
    } else {
      info(
        "预览设置",
        `当前身份：${identity}\n界面统一使用本地思源黑体、19 个语义基础色。\n本页新示例的收藏、学习和任务操作仅保留在本次页面会话，不覆盖探索营或既有任务记录。`,
      )
    }
  }
  const visibleTasks = practiceTasks
    .filter(
      (t) =>
        (menu !== "mine" || taskStatus(t.id) !== "available") &&
        (filter === "全部" || t.category === filter) &&
        `${t.title}${t.category}${t.description}`.includes(query.trim()),
    )
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
  const title = module === "dashboard" ? "探索营" : moduleTitles[module]
  const updateTask = (_id: string, _patch: Partial<PracticeState>) => setNotice("暂未开放")
  return (
    <ModuleBorderProvider decoration={decoration}>
      <div className="module-viewport design-viewport" data-screen={module}>
        <main
          className="module-hub"
          onClickCapture={event=>{
            const target=event.target as HTMLElement;
            if(module!=="dashboard" && target.closest(".module-page-content") && target.closest("button")) {
              const button=target.closest("button");
              if(button?.closest(".module-filterbar") || button?.closest(".module-filter-tabs"))return;
              event.preventDefault();event.stopPropagation();setNotice("暂未开放");
            }
          }}
          data-module={module}
          style={{ zoom: canvasScale }}
        >
          <div className="module-space-background" aria-hidden="true">
            <img src="/assets/project29/home-4062/0ba79.webp" alt="" />
          </div>
          <ModuleSidebar
            module={module}
            onNavigate={onNavigate}
            onLogout={onLogout}
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
                if (menu !== "hall") setMenu("hall")
              }}
              onHome={() => onNavigate("dashboard")}
              onLogout={onLogout}
            />
            {module === "dashboard" ? (
              <div className="module-dashboard-content">{dashboardContent}</div>
            ) : (
              <div
                className="module-page-content"
                ref={pageContent}
                tabIndex={0}
                role="region"
                aria-label={`${title}内容，可滚动查看`}
              >
                {module !== "guild" ? (
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
                        <button
                          className="module-secondary"
                          aria-disabled={module === "village" || undefined}
                          onClick={() =>
                            module === "village"
                              ? undefined
                              : info(
                                  "学习记录",
                                  learned.length
                                    ? academyCourses
                                        .filter((c) => learned.includes(c.id))
                                        .map((c) => `已完成 · ${c.title}`)
                                        .join("\n") +
                                        `\n本次演示经验：${learned.length * 50} XP，未写入正式账户。`
                                    : "本次会话还没有完成的课程。查看课程介绍后，可以标记当前学习完成。",
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
                          if (module === "village")
                            setDialog({
                              type: "task",
                              task: accepted[0] || practiceTasks[0],
                            })
                          else
                            setDialog({
                              type: "course",
                              course:
                                academyCourses.find(
                                  (c) =>
                                    !c.unavailable && !learned.includes(c.id),
                                ) || academyCourses[0],
                            })
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
                              ? "本周实践目标"
                              : "本周探索任务"}
                          </h3>
                          <ModuleIcon
                            file={module === "village" ? "d7bdc" : "d7bdc"}
                            size={30}
                          />
                        </div>
                        <p className="module-weekly-count">
                          <strong>
                            —
                          </strong>
                          <span>
                            / — {module === "village" ? "个任务" : "门课程"}
                          </span>
                        </p>
                        <div
                          className="module-progress-track"
                          role="progressbar"
                          aria-label="本周进度"
                          aria-valuemin={0}
                          aria-valuemax={3}
                          aria-valuetext="暂未开放"
                        >
                          <i
                            style={{
                              width: `${(Math.min(module === "village" ? completed.length : learned.length, 3) / 3) * 100}%`,
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
                            暂未开放
                          </span>
                        </div>
                        <blockquote>
                          暂未开放
                        </blockquote>
                      </ModulePanel>
                    </div>
                    <div ref={listing} className="module-listing">
                      <div className="module-filterbar">
                        <div
                          className="module-tabs"
                          role="group"
                          aria-label={
                            module === "village" ? "任务分类" : "课程分类"
                          }
                        >
                          {(module === "village"
                            ? [
                                "全部",
                                "产品开发",
                                "技术开发",
                                "数据交付",
                                "PMO",
                                "AI 评测",
                                "质量检测",
                              ]
                            : ["全部", "管理员外链", "平台视频", "员工共建"]
                          ).map((category) => (
                            <button
                              key={category}
                              className={filter === category ? "is-active" : ""}
                              aria-pressed={filter === category}
                              onClick={() => setFilter(category)}
                            >
                              {category === "全部"
                                ? module === "village"
                                  ? "全部任务"
                                  : "全部课程"
                                : category}
                              <span>
                                {module === "village"
                                  ? practiceTasks.filter(
                                      (t) =>
                                        category === "全部" ||
                                        t.category === category,
                                    ).length
                                  : academyCourses.filter(
                                      (c) =>
                                        category === "全部" ||
                                        c.category === category,
                                    ).length}
                              </span>
                            </button>
                          ))}
                        </div>
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
                                  : "选择一个方向，完成你的第一次实践"
                              }`
                            : `${visibleCourses.length} 门课程 · ${
                                menu === "saved"
                                  ? "我的收藏"
                                  : "首次完成获得探索经验，每门课程仅结算一次"
                              }`}
                        </span>
                        <span className="module-demo-label">
                          暂未开放
                        </span>
                      </div>
                      {module === "village" ? (
                        <div className="module-cards-grid">
                          {visibleTasks.map((task, index) => (
                            <ModulePanel
                              className="module-task-card"
                              key={task.id}
                            >
                              <div className="module-row">
                                <span className="module-tag">
                                  {task.category}
                                </span>
                                <ModuleStatus status={taskStatus(task.id)} />
                              </div>
                              <button
                                className="module-card-title"
                                onClick={() =>
                                  setDialog({ type: "task", task })
                                }
                              >
                                {task.title}
                              </button>
                              <time className="module-small module-muted">
                                示例发布 · 2026/10/
                                {18 - practiceTasks.indexOf(task)} 10:30
                              </time>
                              <p className="module-card-description">
                                {task.description}
                              </p>
                              <div className="module-meta">
                                <span>{task.level}</span>
                                <span>{task.minutes} 分钟</span>
                                <span>{task.review}</span>
                              </div>
                              <div className="module-reward-box">
                                <div className="module-rewards">
                                  {[
                                    ["经验值", task.experience],
                                    ["任务点", task.points],
                                    ["徽章点", task.points],
                                  ].map(([label, value]) => (
                                    <div key={label}>
                                      <small>{label}</small>
                                      <strong>+{value}</strong>
                                    </div>
                                  ))}
                                </div>
                                {task.badges.map(([badge, percent]) => (
                                  <div
                                    className="module-badge-allocation"
                                    key={badge}
                                  >
                                    <span>
                                      {badge}徽章 <small>{percent}%</small>
                                    </span>
                                    <span>
                                      +{(task.points * percent) / 100} 点
                                    </span>
                                  </div>
                                ))}
                              </div>
                              <div className="module-card-footer">
                                <div className="module-author">
                                  <span className="module-avatar">
                                    {task.mentor[0]}
                                  </span>
                                  <span>
                                    {task.mentor}
                                    <small>任务发布人</small>
                                  </span>
                                </div>
                                <button
                                  onClick={() =>
                                    setDialog({ type: "task", task })
                                  }
                                >
                                  查看任务 →
                                </button>
                              </div>
                            </ModulePanel>
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
                                  <button
                                    className={`module-favorite${
                                      favorites.includes(course.id)
                                        ? " is-saved"
                                        : ""
                                    }`}
                                    aria-label={`${
                                      favorites.includes(course.id)
                                        ? "取消收藏"
                                        : "收藏"
                                    } ${course.title}`}
                                    aria-pressed={favorites.includes(course.id)}
                                    onClick={() =>
                                      setFavorites((previous) =>
                                        previous.includes(course.id)
                                          ? previous.filter(
                                              (id) => id !== course.id,
                                            )
                                          : [...previous, course.id],
                                      )
                                    }
                                  >
                                    <ModuleIcon
                                      file={
                                        favorites.includes(course.id)
                                          ? "b5cc7"
                                          : "cdc4e"
                                      }
                                      size={21}
                                    />
                                  </button>
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
                        ? !visibleTasks.length
                        : !visibleCourses.length) && (
                        <ModulePanel className="module-empty">
                          <h3>
                            暂未开放
                          </h3>
                          <p>该板块暂未开放。</p>
                          <button
                            className="module-secondary"
                            onClick={() => {
                              setMenu("hall")
                              setFilter("全部")
                              setQuery("")
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
                        "三个新板块统一使用 19 个语义基础色，标签沿用探索营的状态规范：进行中为青色，待审核为金色，已完成为绿色，待解锁为灰蓝。插画与照片保留设计原貌，不计入界面配色。新示例操作仅在本次会话中体验；原有探索营和发布任务记录不受影响。",
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
            className="module-dialog"
            onCancel={() => setDialog(null)}
            onClick={(event) => {
              if (event.target === event.currentTarget) setDialog(null)
            }}
          >
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
            {dialog?.type === "task" && (
              <>
                <div className="module-row">
                  <span className="module-tag">{dialog.task.category}</span>
                  <ModuleStatus status={taskStatus(dialog.task.id)} />
                </div>
                <h2>{dialog.task.title}</h2>
                <p>{dialog.task.description}</p>
                <div className="module-meta">
                  <span>{dialog.task.level}</span>
                  <span>{dialog.task.minutes} 分钟</span>
                  <span>{dialog.task.review}</span>
                </div>
                <h3>任务要求</h3>
                <ol>
                  {dialog.task.requirements.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ol>
                <h3>通关标准</h3>
                <p>
                  问题理解 30% · 方案完整性 40% · 证据与表达 30%。示例及格线 60
                  分，审核通过后才算完成。
                </p>
                <div className="module-demo-note">
                  这是设计稿中的练习示例。本次接取和提交不写入正式账户，也不会调用
                  AI
                  或自动通过审核。
                </div>
                {taskStatus(dialog.task.id) === "available" ? (
                  <button
                    className="module-primary"
                    onClick={() =>
                      updateTask(dialog.task.id, { status: "active" })
                    }
                  >
                    接取任务 →
                  </button>
                ) : (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault()
                      const answer = practice[dialog.task.id]?.answer || ""
                      if (answer.trim().length < 20) {
                        setNotice("请填写至少 20 个字的成果说明或作品链接。")
                        return
                      }
                      updateTask(dialog.task.id, { status: "pending" })
                      setNotice(
                        "本次演示提交已进入待审核，不会自动完成或发放奖励。",
                      )
                    }}
                  >
                    <label className="module-field">
                      成果说明或作品链接
                      <textarea
                        required
                        minLength={20}
                        rows={5}
                        disabled={taskStatus(dialog.task.id) === "pending"}
                        value={practice[dialog.task.id]?.answer || ""}
                        onChange={(e) =>
                          updateTask(dialog.task.id, { answer: e.target.value })
                        }
                        placeholder="写下你的分析过程、结果与作品链接…"
                      />
                    </label>
                    <button
                      className="module-primary"
                      disabled={taskStatus(dialog.task.id) === "pending"}
                    >
                      {taskStatus(dialog.task.id) === "pending"
                        ? "已提交，等待审核"
                        : "提交当前"}
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
                      学习完成仅用于本次会话演示。
                    </div>
                    <button
                      className="module-primary"
                      disabled={learned.includes(dialog.course.id)}
                      onClick={() => {
                        const id = dialog.course.id
                        setLearned((prev) =>
                          prev.includes(id) ? prev : [...prev, id],
                        )
                        setNotice(
                          "当前学习已完成，+50 XP（仅演示，不写入正式经验）。",
                        )
                      }}
                    >
                      {learned.includes(dialog.course.id)
                        ? "当前已完成"
                        : "标记当前学习完成"}
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
            {dialog?.type === "share" && (
              <>
                <h2>分享我的发现</h2>
                <p>分享一份可复用的方法或资源，让好经验在学院流动。</p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    const form = new FormData(e.currentTarget)
                    const url = String(form.get("url"))
                    if (!/^https?:\/\//i.test(url)) {
                      setNotice("请填写 http:// 或 https:// 开头的资源链接。")
                      return
                    }
                    setShared((previous) => [
                      ...previous,
                      { title: String(form.get("title")), url },
                    ])
                    setDialog(null)
                    setNotice("共建提案已加入本次演示列表，尚未发送至后台。")
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
                    仅创建本次会话的演示提案，不会发布到公开课程列表。
                  </div>
                  <button className="module-primary">提交演示提案</button>
                </form>
              </>
            )}
          </dialog>
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
            "我的公会身份 · 示例",
            `学员 ${identity} · ${guild} 岗位公会\n等级 L2 · 交付实践者\n已验收作品 1 件 · 公会贡献 20\n这些是设计展示数据，不代表你的正式认证结果。`,
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
                    "陈远 · 交付与协同\n周予安 · 数据质量\n许嘉宁 · 风险管理\n以上为示例导师，未提供真实联系方式。",
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
