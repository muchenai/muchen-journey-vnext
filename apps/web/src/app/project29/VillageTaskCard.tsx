import { ModulePanel, ModuleStatus } from "./ModuleShell"
import type { VillageTask } from "./useVillageTasks"

export const pointNames: Record<string, string> = {
  product: "产品开发", data: "数据交付", tech: "技术开发", pmo: "PMO",
  "ai-eval": "AI评测", quality: "质量检测", project: "项目管理", ai: "AI 能力",
  "it-service": "IT服务", "talent-acquisition": "人才开发", "talent-development": "人才发展",
  "customer-growth": "客户增长", "hr-compensation": "人事薪酬", "finance-compliance": "财法合规",
  "organization-development": "组织发展", "intelligent-solutions": "智能产品方案",
  workplace: "行政职场", "business-operations": "综合经营",
}

// The publication API owns allocation and rounding; task points are not badge points.
export function VillageTaskCard({ task, onOpen }: { task: VillageTask; onOpen: () => void }) {
  const rewards = task.rewardAllocations ?? []
  return <ModulePanel className="module-task-card">
    <div className="module-row"><div className="task-department-labels" aria-label="发布部门"><span className="module-tag">{task.publishingDepartment || "部门待补充"}</span></div><ModuleStatus status={task.status} /></div>
    <button className="module-card-title" onClick={onOpen}>{task.title}</button>
    <time className="module-small module-muted" dateTime={task.publishedAt}>{new Date(task.publishedAt).toLocaleString("zh-CN")}</time>
    <p className="module-card-description">{task.description}</p>
    <div className="module-meta"><span>{task.category}</span><span>{task.level}</span><span>{task.minutes} 分钟</span><span>{task.review}</span></div>
    <div className="module-reward-box">
      <div className="module-rewards">
        <div><small>经验值</small><strong>+{task.experience} XP</strong></div>
        <div><small>徽章点</small><strong>{rewards.length} 种类型</strong></div>
      </div>
      <VillageBadgeAllocations task={task} />
    </div>
    <div className="module-card-footer">
      <div className="module-author"><span className="module-avatar">{task.mentor[0]}</span><span>{task.mentor}<small>任务发布人</small></span></div>
      <button onClick={onOpen}>查看任务 →</button>
    </div>
  </ModulePanel>
}

function VillageBadgeAllocations({ task }: { task: VillageTask }) {
  const rewards = task.rewardAllocations ?? []
  return <>
    {rewards.map(reward => <div className="module-badge-allocation" key={reward.id}>
      <span>{pointNames[reward.id] ?? "其他"}徽章点</span><span>+{reward.points} 点</span>
    </div>)}
    {!rewards.length && <p className="module-small module-muted">暂未配置徽章点</p>}
  </>
}

export function VillageTaskRewards({ task }: { task: VillageTask }) {
  return <>
    <h3>审核通过后的奖励</h3>
    <div className="module-task-reward-preview">
      <p>经验值：<strong>+{task.experience} XP</strong></p>
      <VillageBadgeAllocations task={task} />
      <small>仅发放经验值和发布者配置的分类型徽章点。提交后仍需审核，不会提前发放。</small>
    </div>
  </>
}
