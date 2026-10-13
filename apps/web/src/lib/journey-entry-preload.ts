export const JOURNEY_ENTRY_RESOURCES = [
  "/assets/project9/04543.png",
  "/assets/project9/04604.svg",
  "/assets/project9/048f7.svg",
  "/assets/project9/0b3ec.svg",
  "/assets/project9/0b881.svg",
  "/assets/project9/0c76d.svg",
  "/assets/project9/0ccf1.png",
  "/assets/project9/11489.svg",
  "/assets/project9/17286.svg",
  "/assets/project9/1bed3.svg",
  "/assets/project9/29038.svg",
  "/assets/project9/29dd9.svg",
  "/assets/project9/37de3.svg",
  "/assets/project9/3ba37.svg",
  "/assets/project9/40565.svg",
  "/assets/project9/42137.svg",
  "/assets/project9/4fc5a.svg",
  "/assets/project9/54dd9.svg",
  "/assets/project9/59316.svg",
  "/assets/project9/608f9.svg",
  "/assets/project9/63e0c.svg",
  "/assets/project9/643cc.svg",
  "/assets/project9/69feb.svg",
  "/assets/project9/6f233.png",
  "/assets/project9/7545d.svg",
  "/assets/project9/79dce.svg",
  "/assets/project9/82501.png",
  "/assets/project9/8e84d.svg",
  "/assets/project9/90975.png",
  "/assets/project9/96be2.png",
  "/assets/project9/a1566.svg",
  "/assets/project9/a49bf.svg",
  "/assets/project9/aa530.svg",
  "/assets/project9/ab5ac.svg",
  "/assets/project9/b8c95.svg",
  "/assets/project9/baa53.png",
  "/assets/project9/c21d5.png",
  "/assets/project9/cec96.svg",
  "/assets/project9/cfbf2.svg",
  "/assets/project9/d6a61.png",
  "/assets/project9/eec40.svg",
  "/assets/project9/f4e78.svg",
  "/assets/project9/f6723.svg",
  "/assets/project9/fa18e.png",
  "/assets/project9/dashboard-2047/07842.png",
  "/assets/project9/dashboard-2047/0b3ec.svg",
  "/assets/project9/dashboard-2047/0b881.svg",
  "/assets/project9/dashboard-2047/11489.svg",
  "/assets/project9/dashboard-2047/29038.svg",
  "/assets/project9/dashboard-2047/40565.svg",
  "/assets/project9/dashboard-2047/54dd9.svg",
  "/assets/project9/dashboard-2047/5555c.svg",
  "/assets/project9/dashboard-2047/608f9.svg",
  "/assets/project9/dashboard-2047/63e0c.svg",
  "/assets/project9/dashboard-2047/7545d.svg",
  "/assets/project9/dashboard-2047/c8f76.png",
  "/assets/project9/dashboard-2047/cec96.svg",
  "/assets/project9/dashboard-2047/cfbf2.svg",
  "/assets/project9/dashboard-2047/d01e9.svg",
  "/assets/project9/execution/59316.svg",
  "/fonts/project9/SourceHanSansSC-VF.woff2",
  "/vendor/feishu/h5-js-sdk-1.5.26.csp.js",
] as const;

type FetchResource = (input: string, init: RequestInit) => Promise<Pick<Response, "ok" | "arrayBuffer">>;

export async function preloadJourneyEntryResources(
  onProgress: (loaded: number, total: number) => void,
  signal: AbortSignal,
  fetchResource: FetchResource = fetch,
): Promise<void> {
  const resources = [...JOURNEY_ENTRY_RESOURCES];
  let next = 0;
  let loaded = 0;
  let failed = false;
  onProgress(0, resources.length);

  async function worker() {
    while (!signal.aborted) {
      const index = next++;
      if (index >= resources.length) return;
      try {
        const response = await fetchResource(resources[index], {
          cache: "force-cache",
          credentials: "same-origin",
          signal,
        });
        if (!response.ok) throw new Error("RESOURCE_UNAVAILABLE");
        await response.arrayBuffer();
        loaded += 1;
        onProgress(loaded, resources.length);
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
