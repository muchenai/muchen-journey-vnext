import "./taskClassifications.css";
import { ModulePanel } from "./ModuleShell";
import type { VillageTask } from "./useVillageTasks";
import { belongsToDepartment, taskBadgePointTypes, taskDepartments, type TaskDepartmentFilter } from "./taskDepartments";
import { villageTaskStatusOptions, type VillageTaskStatusFilter } from "./villageTaskList";

export function TaskClassifications({ tasks, department, level, review, badgeType, status, visibleCount, onDepartment, onLevel, onReview, onBadgeType, onStatus, onReset }: {
  tasks: VillageTask[];
  department: TaskDepartmentFilter;
  level: string;
  review: string;
  badgeType: string;
  status?: VillageTaskStatusFilter;
  visibleCount?: number;
  onDepartment: (id: TaskDepartmentFilter) => void;
  onLevel: (level: string) => void;
  onReview: (review: string) => void;
  onBadgeType: (type: string) => void;
  onStatus?: (status: VillageTaskStatusFilter) => void;
  onReset: () => void;
}) {
  const published = tasks;
  const options: { id: TaskDepartmentFilter; name: string }[] = [
    { id: "all", name: "全部部门" },
    { id: "functional", name: "综合职能公会" },
    ...taskDepartments.filter(item => !item.delivery),
    { id: "delivery", name: "交付线（全部）" },
    ...taskDepartments.filter(item => item.delivery),
  ];
  return <ModulePanel className="task-classifications">
    <div className="task-classifications-heading"><div><h3>按适用部门找任务</h3><p>可组合筛选部门、难度、审核方式与徽章点类型；奖励类型不作为部门归属依据。</p></div><button onClick={onReset}>清空筛选</button></div>
    <div className="task-department-options" role="group" aria-label="任务适用部门">
      {options.map(item => <button key={item.id} className={department === item.id ? "is-active" : ""} aria-pressed={department === item.id} onClick={() => onDepartment(item.id)}>
        <span>{item.name}</span><small>{published.filter(task => belongsToDepartment(task, item.id)).length}</small>
      </button>)}
    </div>
    <div className="task-secondary-filters">
      <div className="task-level-options" role="group" aria-label="任务难度"><span>任务难度</span>{["全部", "入门", "进阶", "挑战"].map(item => <button key={item} className={level === item ? "is-active" : ""} aria-pressed={level === item} onClick={() => onLevel(item)}>{item === "全部" ? "全部难度" : item}</button>)}</div>
      <label>审核方式<select value={review} aria-label="任务审核方式" onChange={event => onReview(event.target.value)}><option value="全部">全部方式</option><option>AI 自测</option><option>人工审核</option></select></label>
      <label>徽章点类型<select value={badgeType} aria-label="任务奖励徽章点类型" onChange={event => onBadgeType(event.target.value)}><option value="全部">全部类型</option>{taskBadgePointTypes.map(type => <option key={type} value={type}>{type}徽章点</option>)}</select></label>
      {status !== undefined && onStatus && <label>任务状态<select value={status} aria-label="我的任务状态" onChange={event => onStatus(event.target.value as VillageTaskStatusFilter)}>{villageTaskStatusOptions.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>}
      <span className="task-classification-count" role="status">{visibleCount ?? published.length} 个任务</span>
    </div>
    <p className="task-department-preview-note">按管理端发布时选择的部门筛选；交付线（全部）包含七条交付线。</p>
  </ModulePanel>;
}
