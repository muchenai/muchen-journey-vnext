import { useLayoutEffect, useState, type RefObject } from "react";

export type CanvasDialogRect = { left: number; top: number; width: number; height: number };
export type CanvasDialogBounds = CanvasDialogRect & { scale: number };
type ViewportSize = { width: number; height: number };

/** Keep the top-layer modal inside the visible part of its design canvas. */
export function canvasDialogBounds(
  canvas: CanvasDialogRect | null,
  logicalWidth: number,
  viewport: ViewportSize,
): CanvasDialogBounds | null {
  if (![viewport.width, viewport.height].every(value => Number.isFinite(value) && value > 0)) return null;
  // Standalone consumers without a design canvas use the browser viewport.
  if (!canvas) return { left: 0, top: 0, width: viewport.width, height: viewport.height, scale: 1 };
  if (![canvas.left, canvas.top, canvas.width, canvas.height, logicalWidth].every(Number.isFinite)
    || canvas.width <= 0 || canvas.height <= 0 || logicalWidth <= 0) return null;
  const left = Math.max(0, canvas.left);
  const top = Math.max(0, canvas.top);
  const width = Math.min(viewport.width, canvas.left + canvas.width) - left;
  const height = Math.min(viewport.height, canvas.top + canvas.height) - top;
  if (width <= 0 || height <= 0) return null;
  return { left, top, width, height, scale: canvas.width / logicalWidth };
}

const variableNames = ["left", "top", "width", "height", "scale"] as const;
const canvasSelector = ".design-stage.journey-scaled-canvas, .module-hub.journey-scaled-canvas";

/** Returns true after synchronous bounds are ready, before showModal runs. */
export function useCanvasDialogBounds(ref: RefObject<HTMLDialogElement | null>, open: boolean): boolean {
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    const current = ref.current;
    if (!current) return;
    const dialog: HTMLDialogElement = current;
    const clearVariables = () => {
      for (const name of variableNames) dialog.style.removeProperty(`--ex-modal-${name}`);
    };
    if (!open) {
      clearVariables();
      return;
    }
    let disposed = false;
    let frame: number | null = null;
    let observedCanvases: HTMLElement[] = [];
    const observer = new ResizeObserver(() => schedule());

    function measure() {
      if (disposed) return;
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const candidates = Array.from(document.querySelectorAll<HTMLElement>(canvasSelector));
      let bounds: CanvasDialogBounds | null = null;
      let largestArea = 0;
      for (const canvas of candidates) {
        const rect = canvas.getBoundingClientRect();
        const candidate = canvasDialogBounds(rect, canvas.offsetWidth, viewport);
        if (candidate && candidate.width * candidate.height > largestArea) {
          bounds = candidate;
          largestArea = candidate.width * candidate.height;
        }
      }
      if (!candidates.length) bounds = canvasDialogBounds(null, 0, viewport);
      if (candidates.length !== observedCanvases.length
        || candidates.some((canvas, index) => canvas !== observedCanvases[index])) {
        observer.disconnect();
        observedCanvases = candidates;
        // Observe unpainted candidates too: a stylesheet can give a mounted
        // canvas its first dimensions without another DOM mutation or resize.
        for (const canvas of observedCanvases) observer.observe(canvas);
      }
      if (!bounds) {
        setReady(false);
        return;
      }
      for (const name of variableNames) {
        const value = `${bounds[name]}${name === "scale" ? "" : "px"}`;
        const property = `--ex-modal-${name}`;
        if (dialog.style.getPropertyValue(property) !== value) dialog.style.setProperty(property, value);
      }
      setReady(true);
    }

    function schedule() {
      if (disposed || frame !== null) return;
      frame = window.requestAnimationFrame(() => { frame = null; measure(); });
    }

    function onScroll(event: Event) {
      // Scrolling task content cannot change the surrounding canvas bounds.
      if (event.target instanceof Node && dialog.contains(event.target)) return;
      schedule();
    }

    const rootObserver = new MutationObserver(schedule);
    rootObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
    const sceneObserver = new MutationObserver(records => {
      if (records.some(record => !dialog.contains(record.target))) schedule();
    });
    if (document.body) sceneObserver.observe(document.body, {
      subtree: true, childList: true, attributes: true, attributeFilter: ["hidden"],
    });
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", onScroll, true);
    measure();
    return () => {
      disposed = true;
      if (frame !== null) window.cancelAnimationFrame(frame);
      observer.disconnect();
      rootObserver.disconnect();
      sceneObserver.disconnect();
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", onScroll, true);
      clearVariables();
    };
  }, [ref, open]);
  return open && ready;
}
