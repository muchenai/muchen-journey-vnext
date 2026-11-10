export type ProfileWallet = {
  xp: number;
  availableXp: number;
  redeemedXp: number;
  ownedMedalCount: number;
  badgeBalances: Record<string, number>;
};

export type GrowthEntry = {
  id: string;
  kind: "task_reward" | "medal_redemption";
  occurredAt: string;
  module: string;
  title: string;
  taskId?: string;
  xp: number;
  badgePoints: { id: string; points: number }[];
  medal?: { id: string; name: string };
  method: string;
};

export type GrowthPage = {
  items: GrowthEntry[];
  total: number;
  hasMore: boolean;
  nextOffset: number | null;
};

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const integer = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value);

export const XP_PER_GROWTH_LEVEL = 500;

// Levels use lifetime task rewards, independently of any spendable XP balance.
export function profileGrowthLevel(lifetimeXp: number | undefined) {
  if (!count(lifetimeXp)) return null;
  const level = Math.floor(lifetimeXp / XP_PER_GROWTH_LEVEL) + 1;
  const progress = lifetimeXp % XP_PER_GROWTH_LEVEL;
  return {
    level,
    nextLevel: level + 1,
    title: level <= 2 ? "成长探索者" : "成长实践者",
    progress,
    step: XP_PER_GROWTH_LEVEL,
    remaining: XP_PER_GROWTH_LEVEL - progress,
  };
}

export function parseProfileWallet(value: unknown): ProfileWallet {
  if (!record(value) || !count(value.xp) || !count(value.availableXp) || !count(value.redeemedXp)
    || !count(value.ownedMedalCount) || !record(value.badgeBalances)
    || !Object.values(value.badgeBalances).every(integer)) {
    throw new Error("成长数据不完整，请重新加载。");
  }
  return value as ProfileWallet;
}

export function parseGrowthPage(value: unknown): GrowthPage {
  if (!record(value) || !count(value.total) || typeof value.hasMore !== "boolean"
    || !(value.nextOffset === null || count(value.nextOffset)) || !Array.isArray(value.items)) {
    throw new Error("成长明细读取失败，请重试。");
  }
  for (const item of value.items) {
    if (!record(item) || typeof item.id !== "string" || !item.id
      || !["task_reward", "medal_redemption"].includes(String(item.kind))
      || typeof item.occurredAt !== "string" || !Number.isFinite(Date.parse(item.occurredAt))
      || typeof item.title !== "string" || typeof item.module !== "string" || typeof item.method !== "string"
      || !integer(item.xp) || !Array.isArray(item.badgePoints)
      || !item.badgePoints.every(point => record(point) && typeof point.id === "string" && integer(point.points))
      || (item.medal !== undefined && (!record(item.medal) || typeof item.medal.id !== "string" || typeof item.medal.name !== "string"))) {
      throw new Error("成长明细数据不完整，请重试。");
    }
  }
  if (value.hasMore && (!count(value.nextOffset) || value.nextOffset === 0)) throw new Error("成长明细分页异常，请重新加载。");
  return value as GrowthPage;
}

export async function readGrowthPage(offset: number, signal: AbortSignal): Promise<GrowthPage> {
  if (!count(offset)) throw new Error("成长明细分页异常，请重新加载。");
  const response = await fetch(`/api/learner/profile/history?offset=${offset}&limit=20`, {
    credentials: "same-origin", cache: "no-store", signal,
  });
  const data: unknown = await response.json();
  if (!response.ok) throw new Error(record(data) && typeof data.error === "string" ? data.error : "成长明细读取失败，请重试。");
  const page = parseGrowthPage(data);
  if (page.hasMore && page.nextOffset! <= offset) throw new Error("成长明细分页异常，请重新加载。");
  return page;
}

export const formatGrowthCount = (value: number | undefined) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
export const formatGrowthDelta = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toLocaleString("zh-CN")}`;
