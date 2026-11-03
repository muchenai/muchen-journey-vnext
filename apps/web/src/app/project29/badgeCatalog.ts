import catalogData from "./badgeCatalogData.json";
import type { Badge } from "./badgeEconomy";
import { badgeArtworkFor, badgeGrades, type BadgeArtworkLevel } from "./badgeArtwork";

export type BadgeCatalogArtwork = typeof catalogData[number];
export type BadgeCatalogEntry = { artwork: BadgeCatalogArtwork; publication?: Badge };
export type BadgeCatalogGroup = "all" | "points" | "delivery" | "general";
export const badgeCatalogEntries: BadgeCatalogEntry[] = catalogData.map(artwork => ({ artwork }));
export const badgeCatalogGroups: { id: BadgeCatalogGroup; name: string }[] = [
  { id: "all", name: "全部" }, { id: "points", name: "专业徽章点" },
  { id: "delivery", name: "交付线" }, { id: "general", name: "通用成长" },
];
export const badgeCatalogCategories = [...new Map(catalogData.map(artwork => [
  artwork.categoryId, { id: artwork.categoryId, name: artwork.categoryName, group: artwork.section },
])).values()];

export function connectBadgeCatalog(badges: readonly Badge[], owned: readonly string[]) {
  return badgeCatalogEntries.map(({ artwork }) => {
    const matches = badges.filter(badge => badgeArtworkFor(badge)?.path === artwork.path);
    // If multiple real levels use one artwork, show the highest actually owned level.
    const acquired = matches.filter(badge => owned.includes(badge.id))
      .sort((a, b) => badgeGrades[b.tone].level - badgeGrades[a.tone].level);
    return { artwork, publication: acquired[0] || matches.find(badge => badge.published) };
  });
}

export function filterBadgeCatalog(group: BadgeCatalogGroup = "all", category = "all", query = "", entries = badgeCatalogEntries) {
  const search = query.trim().toLowerCase();
  return entries.filter(({ artwork, publication }) =>
    (group === "all" || artwork.section === group) &&
    (category === "all" || artwork.categoryId === category) &&
    `${artwork.id} ${artwork.name} ${artwork.description} ${artwork.categoryName} ${artwork.sectionName} ${publication?.name || ""}`.toLowerCase().includes(search));
}

export function catalogDisplayLevel(entry: BadgeCatalogEntry, owned: readonly string[]): BadgeArtworkLevel {
  return entry.publication && owned.includes(entry.publication.id) ? badgeGrades[entry.publication.tone].level : 0;
}
