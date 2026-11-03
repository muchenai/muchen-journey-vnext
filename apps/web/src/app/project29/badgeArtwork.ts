import catalog from "./badgeCatalogData.json";
import type { Badge } from "./badgeEconomy";

export type BadgeArtworkLevel = 0 | 1 | 2 | 3;
export const badgeGrades = {
  cyan: { level: 1, label: "一级" },
  violet: { level: 2, label: "二级" },
  gold: { level: 3, label: "三级" },
  // Existing green publications retain their original artwork and style.
  green: { level: 1, label: "成长徽章" },
} as const;

// Only explicit IDs or an exact catalog asset URL establish a relationship.
// A matching name, reward type or list position is not proof of a publication.
export function badgeArtworkFor(badge: Pick<Badge, "artworkId" | "image" | "tone">, locked = false) {
  const artwork = catalog.find(item => item.id === badge.artworkId ||
    ["locked", "level-1", "level-2", "level-3"].some(level =>
      badge.image === `/assets/journey-badges/badges/${level}/${item.path}.webp`));
  return artwork ? { path: artwork.path, level: locked ? 0 as const : badgeGrades[badge.tone].level } : null;
}
