import { pointTypeIds } from "./badgeEconomy";
import type { VillageTask } from "./useVillageTasks";

export { badgePointTypes as taskBadgePointTypes } from "./badgeEconomy";

export const taskDepartments = [
  { id: "it", name: "IT部", delivery: false },
  { id: "talent-development", name: "人才开发部", delivery: false },
  { id: "talent-growth", name: "人才发展部", delivery: false },
  { id: "customer-strategy", name: "客户增长与战略解决方案部", delivery: false },
  { id: "people-payroll", name: "人事运营与薪酬部", delivery: false },
  { id: "finance-compliance", name: "财务法务合规部", delivery: false },
  { id: "hrbp-organization", name: "HRBP与组织发展部", delivery: false },
  { id: "intelligent-products", name: "智能产品方案部", delivery: false },
  { id: "pmo-governance", name: "PMO经营治理办公室", delivery: false },
  { id: "workplace", name: "行政与职场运营部", delivery: false },
  { id: "executive-office", name: "总经办", delivery: false },
  { id: "development", name: "开发部", delivery: false },
  { id: "multilingual", name: "多语种数据交付线", delivery: true },
  { id: "agent-trajectories", name: "Agent交付与行为轨迹交付线", delivery: true },
  { id: "code-reasoning", name: "代码推理交付线", delivery: true },
  { id: "quality-data", name: "高质量数据构建交付线", delivery: true },
  { id: "multimodal", name: "多模态数据交付线", delivery: true },
  { id: "model-evaluation", name: "通用模型测评交付线", delivery: true },
  { id: "dialect-speech", name: "方言语音交付线", delivery: true },
] as const;
export type TaskDepartmentId = typeof taskDepartments[number]["id"];
export type TaskDepartmentFilter = TaskDepartmentId | "all" | "delivery";
export const taskDepartmentName = (id: string) => id === "all" ? "全部部门" : id === "delivery" ? "交付线（全部）" : taskDepartments.find(item => item.id === id)?.name || id;
export function isTaskDepartmentFilter(id: string): id is TaskDepartmentFilter {
  return id === "all" || id === "delivery" || taskDepartments.some(item => item.id === id);
}
export function belongsToDepartment(task: VillageTask, department: TaskDepartmentFilter) {
  const departments = taskDepartments.filter(item => item.name === task.publishingDepartment).map(item => item.id);
  if (department === "all") return true;
  if (department === "delivery") return departments.some(id => taskDepartments.some(item => item.id === id && item.delivery));
  return departments.includes(department);
}
export function filterDepartmentTasks(tasks: VillageTask[], department: TaskDepartmentFilter, level = "全部", review = "全部", query = "", badgeType = "全部") {
  const search = query.trim().toLowerCase();
  return tasks.filter(task => belongsToDepartment(task, department) &&
    (level === "全部" || task.level === level) &&
    (review === "全部" || task.review === review) &&
    (badgeType === "全部" || (task.rewardAllocations || []).some(reward => pointTypeIds[reward.id] === badgeType && reward.points > 0)) &&
    `${task.title} ${task.description} ${task.category} ${task.publishingDepartment || ""}`.toLowerCase().includes(search));
}
