import { createContext, useContext, type ReactNode } from "react"
import { dashboardStatusLabels } from "./DashboardTaskGrid"
import type { ModuleName } from "./moduleDemoData"
import { SharedModuleNavigation } from "./SharedModuleNavigation"
import { sharedAsset } from "./sharedAsset"
import { ReviewNotificationBell } from "./ReviewNotificationBell"

const BorderContext = createContext<ReactNode>(null)
export function ModuleBorderProvider({
  children,
  decoration,
}: {
  children: ReactNode
  decoration: ReactNode
}) {
  return (
    <BorderContext.Provider value={decoration}>
      {children}
    </BorderContext.Provider>
  )
}
export function ModulePanel({
  children,
  className = "",
  id,
}: {
  children: ReactNode
  className?: string
  id?: string
}) {
  const border = useContext(BorderContext)
  return (
    <section
      id={id}
      className={`module-panel figma-stroke figma-stroke-task ${className}`}
    >
      {border}
      {children}
    </section>
  )
}
export function ModuleIcon({
  file,
  pack = "academy",
  size = 18,
}: {
  file: string
  pack?: ModuleName
  size?: number
}) {
  // Preserve the original SVG shape while using the shared semantic icon color.
  return (
    <span
      className="module-icon"
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        maskImage: `url("${sharedAsset(`/assets/project29/modules/${pack}/${file}.svg`)}")`,
      }}
    />
  )
}
export type ModuleStatusName = keyof typeof dashboardStatusLabels | "available" | "returned" | "unavailable"
export function ModuleStatus({ status }: { status: ModuleStatusName }) {
  const labels = {
    ...dashboardStatusLabels,
    available: "可接取",
    returned: "需修改",
    unavailable: "资源待更新",
  }
  return (
    <span className="module-status" data-status={status}>
      {labels[status]}
    </span>
  )
}
export type ModuleDestination = ModuleName | "dashboard"
const sectionTitles: Record<ModuleDestination, string> = {
  dashboard: "探索营",
  village: "新手村",
  academy: "AI学院",
  guild: "交付线工会",
}
export function ModuleHeader({
  module,
  menu,
  identity,
  query,
  onQuery,
  onHome,
  onLogout,
}: {
  module: ModuleDestination
  menu: string
  identity: string
  query: string
  onQuery: (value: string) => void
  onHome: () => void
  onLogout: () => void
}) {
  const hall = {
    dashboard: "探索营大厅",
    village: "任务大厅",
    academy: "学院大厅",
    guild: "公会大厅",
  }
  const page =
    ({ mine: "我的任务", saved: "我的收藏" } as Record<string, string>)[menu] ||
    hall[module]
  return (
    <header className="module-header">
      <div className="module-breadcrumb">
        <button onClick={onHome}>主页</button>
        <ModuleIcon file="bfb49" size={12} />
        <span>{sectionTitles[module]}</span>
        <ModuleIcon file="bfb49" size={12} />
        <span>{page}</span>
      </div>
      <div className="module-header-tools">
        <label className="module-search">
          <ModuleIcon file="095be" size={17} />
          <input
            aria-label="搜索当前板块"
            placeholder="搜索内容"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
          <kbd>⌘ K</kbd>
        </label>
        <ReviewNotificationBell>
          <ModuleIcon file="99dd2" size={20} />
        </ReviewNotificationBell>
        <button
          className="module-account"
          aria-label="切换身份"
          onClick={onLogout}
        >
          <ModuleIcon file="a2a2a" size={16} />
          <span>{identity}</span>
          <ModuleIcon file="e7bbd" size={10} />
        </button>
      </div>
    </header>
  )
}
export function ModuleSidebar({
  module,
  onNavigate,
  onLogout,
  onMenu,
  activeMenu,
  activeDecoration,
  idleDecoration,
  taskCount = 0,
}: {
  module: ModuleDestination
  onNavigate: (page: ModuleDestination) => void
  onLogout: () => void
  onMenu: (menu: string) => void
  activeMenu: string
  activeDecoration: ReactNode
  idleDecoration: ReactNode
  taskCount?: number
}) {
  const menu =
    module === "dashboard"
      ? [
          ["hall", "探索营大厅", "8c48a"],
          ["tasks", "探索任务", "eec40"],
        ]
      : module === "academy"
        ? [
            ["hall", "学院大厅", "8c48a"],
            ["saved", "我的收藏", "eec40"],
          ]
        : module === "village"
          ? [
              ["hall", "任务大厅", "8c48a"],
              ["mine", "我的任务", "eec40"],
              ["badges", "我的徽章", "a03b5"],
            ]
          : [
              ["hall", "工会大厅", "8c48a"],
              ["certification", "能力认证", "a03b5"],
              ["lab", "模拟实验室", "eec40"],
            ]
  return (
    <SharedModuleNavigation
      module={module}
      onNavigate={onNavigate}
      activeDecoration={activeDecoration}
      idleDecoration={idleDecoration}
    >
      <div className="module-secondary-navigation">
        <nav
          className="module-section-menu"
          aria-label={`${sectionTitles[module]}导航`}
        >
          {menu.map(([id, title, icon]) => (
            <button
              key={id}
              className={activeMenu === id ? "is-active" : ""}
              onClick={() => onMenu(id)}
              aria-current={activeMenu === id ? "page" : undefined}
            >
              <ModuleIcon
                pack={module === "dashboard" ? "academy" : module}
                file={icon}
                size={24}
              />
              {title}
              {module === "dashboard" && id === "tasks" && (
                <span className="module-nav-count">{taskCount}</span>
              )}
            </button>
          ))}
          <button onClick={() => onMenu("map")}>
            <ModuleIcon file="93f75" size={24} />
            世界地图
          </button>
          <button onClick={() => onMenu("knowledge")}>
            <ModuleIcon file="643cc" size={24} />
            知识库
          </button>
          <button onClick={onLogout}>
            <ModuleIcon file="0c76d" size={24} />
            切换身份
          </button>
        </nav>
        <div className="module-sidebar-bottom">
          <div className="module-sidebar-rule" />
          <button onClick={() => onMenu("settings")}>
            <ModuleIcon file="f4e78" size={24} />
            设置
          </button>
          <small>Better People Better Work</small>
        </div>
      </div>
    </SharedModuleNavigation>
  )
}
export function ModuleHero({
  module,
  onContinue,
  onIdentity,
  title,
  subtitle,
  description,
}: {
  module: ModuleName
  onContinue: () => void
  onIdentity?: () => void
  title: string
  subtitle: string
  description: string
}) {
  return (
    <ModulePanel className={`module-hero module-hero-${module}`}>
      <div className="module-hero-art">
        <img src={sharedAsset(`/assets/project29/modules/${module}/96be2.webp`)} alt="" />
      </div>
      <div className="module-hero-shade" />
      <div className="module-hero-content">
        <small className="module-eyebrow">
          {module === "guild"
            ? "专业同行，一起把交付做好"
            : module === "village"
              ? "在实践中学习 · 让成长有迹可循"
              : "探索新知 · 点亮能力星图"}
        </small>
        <h2>
          {title}
          <br />
          <span>{subtitle}</span>
        </h2>
        <p>{description}</p>
        <div className="module-actions">
          <button className="module-primary" onClick={onContinue}>
            {module === "guild"
              ? "继续我的公会进阶"
              : module === "village"
                ? "开始我的第一份任务"
                : "继续我的 AI 探索"}
            <ModuleIcon file="b5042" />
          </button>
          {module === "guild" && (
            <button className="module-hero-identity" onClick={onIdentity}>
              查看公会身份
              <ModuleIcon pack="guild" file="dccc5" size={16} />
            </button>
          )}
        </div>
        {module === "guild" && (
          <div className="module-hero-peers">
            <span className="module-avatar" aria-hidden="true">—</span>
            <span className="module-avatar" aria-hidden="true">—</span>
            <span className="module-avatar" aria-hidden="true">—</span>
            <span className="module-avatar" aria-hidden="true">—</span>
            <small>暂未开放</small>
          </div>
        )}
      </div>
      <small className="module-hero-signature">
        {module === "guild" && (
          <ModuleIcon pack="guild" file="4c175" size={34} />
        )}
        {module === "guild" ? "DELIVERY / GUILD" : "MUCHEN / NEXT POSSIBILITY"}
      </small>
    </ModulePanel>
  )
}
