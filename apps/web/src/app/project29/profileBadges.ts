import { adaptMedals, type Badge, type MedalResponse } from "./badgeEconomy";
import { parseProfileWallet, type ProfileWallet } from "./profileGrowth";

export type ProfileCollection = { wallet: ProfileWallet; badges: Badge[] };

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.length > 0;
const appearance = (value: Record<string, unknown>) => typeof value.image === "string" && text(value.style)
  && (value.artworkId === undefined || typeof value.artworkId === "string")
  && Array.isArray(value.costs) && value.costs.every(cost => record(cost) && text(cost.badgeId)
    && typeof cost.points === "number" && Number.isSafeInteger(cost.points) && cost.points >= 0);

export function parseProfileCollection(value: unknown): ProfileCollection {
  if (!record(value) || !Array.isArray(value.medals) || !Array.isArray(value.redemptions)
    || !value.medals.every(medal => record(medal) && text(medal.id) && text(medal.name)
      && typeof medal.description === "string" && appearance(medal))
    || !value.redemptions.every(item => record(item) && text(item.id) && text(item.medalId)
      && text(item.medalName) && text(item.redeemedAt) && Number.isFinite(Date.parse(item.redeemedAt)) && appearance(item))) {
    throw new Error("徽章数据不完整，请重新加载。");
  }
  const wallet = parseProfileWallet(value.wallet);
  const data = value as MedalResponse;
  const byId = new Map(adaptMedals(data).badges.map(badge => [badge.id, badge]));
  const ownedIds = [...new Set([...data.redemptions]
    .sort((a, b) => Date.parse(b.redeemedAt) - Date.parse(a.redeemedAt))
    .map(item => item.medalId))];
  const badges = ownedIds.map(id => byId.get(id)!);
  if (badges.some(badge => !badge) || wallet.ownedMedalCount !== badges.length) {
    throw new Error("徽章记录正在更新，请重新加载。");
  }
  return { wallet, badges };
}
