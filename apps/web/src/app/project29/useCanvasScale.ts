import { useSyncExternalStore } from "react";

export function canvasScaleFor(width: number, height: number) {
  return Math.min(width / 1920, height / 1080);
}

const readScale = () => canvasScaleFor(window.innerWidth, window.innerHeight);
const serverScale = () => 1;

function subscribeScale(notify: () => void) {
  let frame = 0;
  const update = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(notify);
  };
  window.addEventListener("resize", update);
  document.addEventListener("fullscreenchange", update);
  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("resize", update);
    document.removeEventListener("fullscreenchange", update);
  };
}

// Read the same viewport snapshot immediately on every module mount.
// Layout remains 1920×1080; only the final rendered canvas changes size.
export function useCanvasScale() {
  return useSyncExternalStore(subscribeScale, readScale, serverScale);
}
