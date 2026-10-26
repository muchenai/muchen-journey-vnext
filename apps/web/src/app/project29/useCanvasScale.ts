import { useEffect, useState } from "react";

export function canvasScaleFor(width: number, height: number) {
  return Math.min(width / 1920, height / 1080);
}

// Layout remains 1920×1080; only the final rendered canvas changes size.
export function useCanvasScale() {
  const readScale = () => canvasScaleFor(window.innerWidth, window.innerHeight);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setScale(readScale()));
    };
    update();
    window.addEventListener("resize", update);
    document.addEventListener("fullscreenchange", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      document.removeEventListener("fullscreenchange", update);
    };
  }, []);
  return scale;
}
