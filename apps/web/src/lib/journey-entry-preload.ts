export const JOURNEY_CACHE_NAME = "muchen-journey-entry-v3";
export const JOURNEY_CACHE_PREFIX = "muchen-journey-entry-";

export const JOURNEY_ENTRY_RESOURCES = [
  "/assets/project9/04543.png", "/assets/project9/04604.svg", "/assets/project9/048f7.svg",
  "/assets/project9/0b3ec.svg", "/assets/project9/0b881.svg", "/assets/project9/0c76d.svg",
  "/assets/project9/0ccf1.png", "/assets/project9/11489.svg", "/assets/project9/17286.svg",
  "/assets/project9/1bed3.svg", "/assets/project9/29038.svg", "/assets/project9/29dd9.svg",
  "/assets/project9/37de3.svg", "/assets/project9/3ba37.svg", "/assets/project9/40565.svg",
  "/assets/project9/42137.svg", "/assets/project9/4fc5a.svg", "/assets/project9/54dd9.svg",
  "/assets/project9/59316.svg", "/assets/project9/608f9.svg", "/assets/project9/63e0c.svg",
  "/assets/project9/643cc.svg", "/assets/project9/69feb.svg", "/assets/project9/6f233.png",
  "/assets/project9/7545d.svg", "/assets/project9/79dce.svg", "/assets/project9/82501.png",
  "/assets/project9/8e84d.svg", "/assets/project9/90975.png", "/assets/project9/96be2.png",
  "/assets/project9/a1566.svg", "/assets/project9/a49bf.svg", "/assets/project9/aa530.svg",
  "/assets/project9/ab5ac.svg", "/assets/project9/b8c95.svg", "/assets/project9/baa53.png",
  "/assets/project9/c21d5.png", "/assets/project9/cec96.svg", "/assets/project9/cfbf2.svg",
  "/assets/project9/d6a61.png", "/assets/project9/eec40.svg", "/assets/project9/f4e78.svg",
  "/assets/project9/f6723.svg", "/assets/project9/fa18e.png",
  "/assets/project9/dashboard-2047/07842.png", "/assets/project9/dashboard-2047/0b3ec.svg",
  "/assets/project9/dashboard-2047/0b881.svg", "/assets/project9/dashboard-2047/11489.svg",
  "/assets/project9/dashboard-2047/29038.svg", "/assets/project9/dashboard-2047/40565.svg",
  "/assets/project9/dashboard-2047/54dd9.svg", "/assets/project9/dashboard-2047/5555c.svg",
  "/assets/project9/dashboard-2047/608f9.svg", "/assets/project9/dashboard-2047/63e0c.svg",
  "/assets/project9/dashboard-2047/7545d.svg", "/assets/project9/dashboard-2047/c8f76.png",
  "/assets/project9/dashboard-2047/cec96.svg", "/assets/project9/dashboard-2047/cfbf2.svg",
  "/assets/project9/dashboard-2047/d01e9.svg", "/assets/project9/execution/59316.svg",
  "/fonts/project9/SourceHanSansSC-VF.woff2",
  "/images/exploration-camp-cockpit-reference.png", "/images/exploration-camp-hero-v2.png",
  "/images/exploration-task-material.png", "/images/journey-v2-background.png",
  "/images/journey-v2-material-cover.png", "/images/journey-v2-reopen-icon.svg",
  "/images/journey-v2-submit-icon.svg", "/images/journey-v2-task-icon.png",
  "/images/muchen-journey-group5-bg.png", "/images/muchen-journey-group5-orb.png",
  "/images/muchen-quest-group3-bg.png", "/images/muchen-quest-group3-mark.png",
  "/images/muchen-quest-mark.svg", "/images/muchen-quest-space-hero-v1.png",
  "/journey/day0-threshold-v1.jpg", "/journey/treasure-evidence-compass-v1.webp",
  "/vendor/feishu/h5-js-sdk-1.5.26.csp.js",
] as const;

type FetchResponse = Pick<Response, "ok" | "arrayBuffer"> & Partial<Pick<Response, "clone">>;
type FetchResource = (input: string, init: RequestInit) => Promise<FetchResponse>;
type CacheWriter = { put(input: string, response: Response): Promise<void> };
type CacheStorageLike = {
  open(name: string): Promise<CacheWriter>;
  keys(): Promise<string[]>;
  delete(name: string): Promise<boolean>;
};

export type JourneyPreloadProgress = {
  loaded: number;
  total: number;
  loadedBytes: number;
  resource: string;
};

function runtimeResources(): string[] {
  if (typeof window === "undefined") return [];
  const resources = new Set<string>();
  const add = (value: string) => {
    try {
      const url = new URL(value, window.location.href);
      if (url.origin === window.location.origin && url.pathname.startsWith("/_next/static/")) {
        resources.add(`${url.pathname}${url.search}`);
      }
    } catch { /* Ignore malformed browser performance entries. */ }
  };
  performance.getEntriesByType("resource").forEach(entry => add(entry.name));
  document.querySelectorAll<HTMLScriptElement | HTMLLinkElement>("script[src],link[href]").forEach(element => {
    add(element instanceof HTMLScriptElement ? element.src : element.href);
  });
  return [...resources];
}

export async function prepareJourneyCache(): Promise<void> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  await navigator.serviceWorker.register("/journey-cache-worker.js", { scope: "/" });
  await navigator.serviceWorker.ready;
}

export async function preloadJourneyEntryResources(
  onProgress: (progress: JourneyPreloadProgress) => void,
  signal: AbortSignal,
  fetchResource: FetchResource = fetch,
  cacheStorage: CacheStorageLike | null = typeof caches === "undefined" ? null : caches,
  extraResources: readonly string[] = runtimeResources(),
): Promise<void> {
  const resources = [...new Set([...JOURNEY_ENTRY_RESOURCES, ...extraResources])];
  let next = 0;
  let loaded = 0;
  let loadedBytes = 0;
  let failed = false;
  onProgress({ loaded: 0, total: resources.length, loadedBytes: 0, resource: "" });

  let cache: CacheWriter | null = null;
  if (cacheStorage) {
    const names = await cacheStorage.keys();
    await Promise.all(names
      .filter(name => name.startsWith(JOURNEY_CACHE_PREFIX) && name !== JOURNEY_CACHE_NAME)
      .map(name => cacheStorage.delete(name)));
    cache = await cacheStorage.open(JOURNEY_CACHE_NAME);
  }

  async function worker() {
    while (!signal.aborted) {
      const index = next++;
      if (index >= resources.length) return;
      const resource = resources[index];
      try {
        const response = await fetchResource(resource, {
          cache: "force-cache",
          credentials: "same-origin",
          signal,
        });
        if (!response.ok) throw new Error("RESOURCE_UNAVAILABLE");
        if (cache && response.clone) await cache.put(resource, response.clone() as Response);
        const body = await response.arrayBuffer();
        loadedBytes += body.byteLength;
        loaded += 1;
        onProgress({ loaded, total: resources.length, loadedBytes, resource });
      } catch {
        if (signal.aborted) return;
        failed = true;
      }
    }
  }

  await Promise.all(Array.from({ length: 4 }, () => worker()));
  if (signal.aborted) throw new DOMException("Loading cancelled", "AbortError");
  if (failed || loaded !== resources.length) throw new Error("ENTRY_RESOURCES_UNAVAILABLE");
}
