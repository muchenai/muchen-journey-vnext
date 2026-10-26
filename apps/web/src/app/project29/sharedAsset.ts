import aliases from "./assetAliases.json";

// Dynamically selected module icons and images share byte-identical originals.
export function sharedAsset(url: string): string {
  return (aliases as Record<string, string>)[url] ?? url;
}
