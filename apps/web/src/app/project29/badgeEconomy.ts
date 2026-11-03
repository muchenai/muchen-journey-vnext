export const badgePointTypes = [
  "数据交付", "技术开发", "产品开发", "PMO", "AI评测", "质量检测", "项目管理", "AI能力",
  "IT服务", "人才开发", "人才发展", "客户增长", "人事薪酬",
  "财法合规", "组织发展", "智能产品方案", "行政职场", "综合经营",
] as const;
export type BadgePointType = typeof badgePointTypes[number];
export type BadgePointCost = { type: BadgePointType; amount: number };
export type Badge = {
  id: string;
  name: string;
  category: string;
  level: string;
  icon: string;
  requirements: BadgePointCost[];
  tone: "cyan" | "violet" | "gold" | "green";
  image?: string; revision: number; stock: number | null; published: boolean;
  artworkId?: string;
  description: string;
};
export type BadgeWallet = {
  balances: Record<BadgePointType, number>;
  owned: string[];
  history: { id: string; name: string; costs: BadgePointCost[]; at: string }[];
};
export const badgePointLabel = (type: BadgePointType) => `${type}徽章点`;

export function completeBadgeBalances(balances: Partial<Record<BadgePointType, number>>): Record<BadgePointType, number> {
  return Object.fromEntries(badgePointTypes.map(type => [type, balances[type] ?? 0])) as Record<BadgePointType, number>;
}

export function badgeCostStatus(wallet: BadgeWallet, badge: Badge) {
  const costs = new Map<BadgePointType, number>();
  const requirements = Array.isArray(badge.requirements) ? badge.requirements : [];
  let valid = requirements.length > 0;
  for (const cost of requirements) {
    if (!cost || !badgePointTypes.includes(cost.type) || !Number.isFinite(cost.amount) || cost.amount <= 0 ||
      cost.amount > Number.MAX_SAFE_INTEGER) { valid = false; continue; }
    const amount = (costs.get(cost.type) || 0) + cost.amount;
    if (!Number.isFinite(amount) || amount > Number.MAX_SAFE_INTEGER) valid = false;
    costs.set(cost.type, amount);
  }
  const details = [...costs].map(([type, amount]) => {
    const balance = wallet.balances?.[type];
    const available = Number.isFinite(balance) && balance >= 0 && balance <= Number.MAX_SAFE_INTEGER ? balance : 0;
    return { type, amount, available, missing: Math.max(0, amount - available) };
  });
  return { valid, affordable: valid && details.every(cost => cost.missing === 0), details };
}


export const pointTypeIds: Record<string, BadgePointType> = {
  data: "数据交付", tech: "技术开发", product: "产品开发", pmo: "PMO", "ai-eval": "AI评测", quality: "质量检测", project: "项目管理", ai: "AI能力",
  "it-service": "IT服务", "talent-acquisition": "人才开发", "talent-development": "人才发展", "customer-growth": "客户增长", "hr-compensation": "人事薪酬", "finance-compliance": "财法合规", "organization-development": "组织发展", "intelligent-solutions": "智能产品方案", workplace: "行政职场", "business-operations": "综合经营",
};
export type MedalRecord = { id: string; name: string; description: string; image: string; artworkId?: string; style: string; revision: number; stock: number | null; costs: {badgeId: string; points: number}[] };
export type MedalResponse = { medals: MedalRecord[]; wallet: { badgeBalances: Record<string, number> }; redemptions: { id: string; medalId: string; medalName: string; image: string; artworkId?: string; style: string; costs: MedalRecord["costs"]; redeemedAt: string }[] };
export function adaptMedals(data: MedalResponse): { badges: Badge[]; wallet: BadgeWallet } {
  const costs = (values: MedalRecord["costs"]) => values.map(c => ({type: pointTypeIds[c.badgeId], amount: c.points}));
  const make = (m: MedalRecord, published: boolean): Badge => ({ id:m.id, name:m.name, description:m.description, image:m.image, artworkId:m.artworkId, revision:m.revision, stock:m.stock, published,
    requirements:costs(m.costs), category:pointTypeIds[m.costs[0]?.badgeId] || "徽章", level:"成长徽章", icon:"a03b5", tone:m.style === "gold" ? "gold" : m.style === "purple" || m.style === "violet" ? "violet" : m.style === "green" ? "green" : "cyan" });
  const badges = data.medals.map(m => make(m, true));
  for (const r of data.redemptions) if (!badges.some(b => b.id === r.medalId)) badges.push(make({id:r.medalId, name:r.medalName, description:"已收藏的成长印记", image:r.image, artworkId:r.artworkId, style:r.style, costs:r.costs, revision:0, stock:null}, false));
  return {badges, wallet:{balances:completeBadgeBalances(Object.fromEntries(Object.entries(data.wallet.badgeBalances).map(([id, value]) => [pointTypeIds[id], value]))),
    owned:data.redemptions.map(r => r.medalId), history:data.redemptions.map(r => ({id:r.id, name:r.medalName, costs:costs(r.costs), at:r.redeemedAt}))}};
}
