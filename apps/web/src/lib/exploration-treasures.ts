export type ExplorationTreasureId = "compass" | "crystal" | "starmap" | "key";

export const TREASURE_CATALOG: readonly {
  id: ExplorationTreasureId;
  name: string;
  subtitle: string;
  description: string;
  color: "cyan" | "violet" | "blue" | "gold";
}[] = [
  { id: "compass", name: "晨光罗盘", subtitle: "找到出发的方向", description: "在新的航程里，找到属于自己的方向。", color: "cyan" },
  { id: "crystal", name: "共鸣晶石", subtitle: "让价值彼此照亮", description: "理解共同的价值，让每一次行动产生共鸣。", color: "violet" },
  { id: "starmap", name: "协作星图", subtitle: "连接同行的伙伴", description: "找到同行的伙伴，在协作中探索更远的星系。", color: "blue" },
  { id: "key", name: "远航密钥", subtitle: "打开下一种可能", description: "把学习化为行动，为下一段成长开启新的可能。", color: "gold" },
];

export type ExplorationTreasureDrop = {
  id: string;
  treasureId: ExplorationTreasureId;
  taskId: string;
  taskTitle: string;
  discoveredAt: string;
  acknowledgedAt: string | null;
};

export type ExplorationGraduation = {
  status: "LOCKED" | "AVAILABLE" | "READY" | "MIGRATED" | "NOT_REQUIRED";
  code: string | null;
  unlockedAt: string | null;
  completedTasks?: number;
  totalTasks?: number;
  remainingTasks?: number;
  blockReason?: string | null;
};

export type ExplorationTreasures = {
  total: 4;
  count: number;
  items: ExplorationTreasureDrop[];
  pendingDrops: ExplorationTreasureDrop[];
  graduation?: ExplorationGraduation;
};

export function emptyExplorationTreasures(): ExplorationTreasures {
  return { total: 4, count: 0, items: [], pendingDrops: [], graduation: { status: "LOCKED", code: null, unlockedAt: null } };
}
