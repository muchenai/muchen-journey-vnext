import { adaptMedals, type Badge, type MedalResponse } from "./badgeEconomy";
import { badgeGrades } from "./badgeArtwork";
import { badgeCatalogCategories, connectBadgeCatalog } from "./badgeCatalog";

export type GuildLevel = 0 | 1 | 2 | 3;
export type GuildBadge = Badge & { guildGrade?: GuildLevel };
export const guildBadgeGrade = (badge: GuildBadge): GuildLevel => badge.guildGrade ?? badgeGrades[badge.tone].level;
export type GuildView = "hall" | "certification" | "capability-map" | "arena";
export type GuildHall = { id: string; title: string; type: string; description: string; icon: string; joined: boolean; level: GuildLevel };
export type GuildTask = { id: string; level: 1 | 2 | 3; title: string; difficulty: string; minutes: number; brief: string; deliverable: string; checks: string[]; source: string; version: number; publicationStatus: string; mentor?: string };
export type GuildTaskDraft = { artifact: string; checks: string[]; revision: number };
export type GuildTaskSubmission = GuildTaskDraft & { guildId: string; level: 1 | 2 | 3; taskId: string; submittedAt: string | null; status: "draft" | "submitted" };
export type GuildRequirement = {
  level: 1 | 2 | 3;
  grades: readonly (1 | 2 | 3)[];
  previousMet: boolean;
  eligible: boolean;
  entryEligible: boolean;
  taskSubmitted: boolean;
  fulfilled: number;
  required: number;
  counts?: { grade: 1 | 2 | 3; count: number }[];
};
export type GuildRequest = {
  id: string;
  guildId: string | null;
  level: 1 | 2 | 3;
  status: "pending" | "approved" | "returned";
  evidence: { id: string; name: string; grade: 1 | 2 | 3; redemptionId?: string; artworkId?: string; image?: string }[];
  submittedAt: string;
  reviewedAt: string | null;
  reviewerName: string | null;
  reason: string;
  task?: { id: string; title: string; artifact: string; checks: string[]; submittedAt: string; revision: number } | null;
};
export type GuildSnapshot = {
  joinedGuild: string | null;
  halls: GuildHall[];
  tasks: GuildTask[];
  submissions: GuildTaskSubmission[];
  legacyRequests: GuildRequest[];
  level: GuildLevel;
  levelName: string;
  requirements: GuildRequirement[];
  requests: GuildRequest[];
};
export const guildLevelNames = ["未认证", "基础实践者", "进阶协作者", "综合交付者"] as const;
export const guildStageNames = ["待启用", "规范实践", "协同攻坚", "复杂交付"] as const;
export const guildCertificationRules = [
  { level: 1, title: "规范实践", description: "获得一级徽章，并能按规则完成有证据的实践任务。" },
  { level: 2, title: "协同攻坚", description: "已有规范实践记录，并能在质量、进度和协同冲突中作出判断。" },
  { level: 3, title: "复杂交付", description: "已有协同攻坚记录，并能处理复杂变更、验收与复盘。" },
] as const;
export function guildActiveHall(snapshot: GuildSnapshot) {
  return snapshot.halls.find(hall => hall.id === snapshot.joinedGuild && hall.joined) || null;
}
export const guildTaskScope = (guildId: string, level: number) => `${guildId}:${level}`;
export function guildSubmission(snapshot: GuildSnapshot, guildId: string, level: 1 | 2 | 3) {
  return snapshot.submissions.find(item => item.guildId === guildId && item.level === level);
}
export function guildTaskValidation(task: GuildTask, draft: Pick<GuildTaskDraft, "artifact" | "checks">) {
  if (draft.artifact.trim().length < 60 || draft.artifact.length > 6000) return "请填写 60～6,000 字的任务成果。";
  if (draft.checks.length !== task.checks.length || !task.checks.every(item => draft.checks.includes(item))) return "请逐项完成任务成果自查。";
  return "";
}
export function adaptGuildMedals(data: MedalResponse) {
  const account = adaptMedals(data);
  return { ...account, badges: account.badges.map(badge => {
    const receipt = data.redemptions.find(item => item.medalId === badge.id) as (MedalResponse["redemptions"][number] & { artworkLevel?: number }) | undefined;
    if (!receipt) return badge;
    const grade = [1, 2, 3].includes(receipt.artworkLevel || 0) ? receipt.artworkLevel :
      ({ blue: 1, cyan: 1, green: 1, purple: 2, violet: 2, gold: 3 } as Record<string, number>)[receipt.style];
    return { ...badge, name: receipt.medalName, image: receipt.image, artworkId: receipt.artworkId, guildGrade: (grade || 0) as GuildLevel,
      tone: (grade === 3 ? "gold" : grade === 2 ? "violet" : "cyan") as Badge["tone"] };
  }) };
}
export function guildOwnedBadges(badges: readonly Badge[], owned: readonly string[]) {
  const ids = new Set(owned);
  return badges.filter(badge => ids.has(badge.id));
}
export function guildCapabilityRows(badges: readonly GuildBadge[], owned: readonly string[]) {
  const catalog = connectBadgeCatalog(badges, owned);
  return badgeCatalogCategories.map(category => {
    const entries = catalog.filter(entry => entry.artwork.categoryId === category.id);
    const acquired = entries.filter(entry => entry.publication && owned.includes(entry.publication.id) && guildBadgeGrade(entry.publication) > 0);
    const highest = acquired.reduce<GuildLevel>((value, entry) => Math.max(value, guildBadgeGrade(entry.publication!)) as GuildLevel, 0);
    const representative = acquired.find(entry => guildBadgeGrade(entry.publication!) === highest) || entries[0];
    return { ...category, entries, acquired, highest, representative };
  });
}
export function guildPendingRequest(snapshot: GuildSnapshot, level?: number) {
  return snapshot.requests.find(request => request.guildId === snapshot.joinedGuild && request.status === "pending" && (level === undefined || request.level === level));
}
export function guildCanApply(snapshot: GuildSnapshot, level: 1 | 2 | 3) {
  return !!guildActiveHall(snapshot) && snapshot.level + 1 === level && !guildPendingRequest(snapshot) && snapshot.requirements.some(item => item.level === level && item.eligible && item.taskSubmitted);
}
export const guildCapabilityLabel = (id: string, name: string) => ({
  "delivery-agent": "Agent 轨迹", "delivery-dialect": "方言语音", "delivery-evaluation": "通用模型测评",
  "delivery-multilingual": "多语种数据", "delivery-multimodal": "多模态数据",
  "delivery-quality": "高质量数据", "delivery-reasoning": "代码推理",
}[id] || name.replace(/徽章点$/, ""));
