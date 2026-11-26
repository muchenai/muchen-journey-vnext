// Run synchronously in <head>, before any learner canvas can be painted.
// A CSS variable keeps SSR, hydration and subsequent page mounts at one scale.
export const canvasScaleBootstrap = `(() => {
  const root = document.documentElement;
  const storageKey = 'journey.canvas.viewport.v1';
  let previous = null;
  let browserZoom = 1;
  let scale = 1;
  let moduleScale = 1;
  let moduleZoom = 1;
  let displayDensity;
  const desktopZoomSteps = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5];
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(storageKey) || 'null');
    if (saved && [saved.ratio, saved.outerWidth, saved.outerHeight, saved.zoom].every(Number.isFinite)
        && saved.ratio > 0 && saved.zoom >= 0.1 && saved.zoom <= 10) {
      previous = saved;
      browserZoom = saved.zoom;
    }
  } catch {}
  const setStyle = (property, value) => {
    if (root.style.getPropertyValue(property) !== value) root.style.setProperty(property, value);
  };
  const restore = () => {
    setStyle('--journey-canvas-scale', String(scale));
    setStyle('--journey-canvas-overflow', browserZoom > 1.001 ? 'auto' : 'hidden');
    setStyle('--journey-module-scale', String(moduleScale));
    setStyle('--journey-module-overflow', moduleZoom > 1.001 ? 'auto' : 'hidden');
  };
  const update = () => {
    const { innerWidth, innerHeight } = window;
    if (!innerWidth || !innerHeight) return;
    const ratio = window.devicePixelRatio || 1;
    const outerWidth = window.outerWidth || window.innerWidth;
    const outerHeight = window.outerHeight || window.innerHeight;
    // Browser zoom changes CSS viewport dimensions and DPR while the window
    // stays the same size. Do not cancel the user's zoom by fitting again.
    if (previous && Math.abs(outerWidth - previous.outerWidth) <= 2
        && Math.abs(outerHeight - previous.outerHeight) <= 2) {
      browserZoom = Math.max(0.1, Math.min(10, browserZoom * ratio / previous.ratio));
    }
    const fit = Math.min(innerWidth / 1920, innerHeight / 1080);
    scale = fit * browserZoom;
    // The four learner modules use the Academy's actual desktop zoom, even
    // when entering the first module with a stale zoom saved in this tab.
    const widthRatio = window.outerWidth / innerWidth;
    const step = desktopZoomSteps.reduce((nearest, value) =>
      Math.abs(value - widthRatio) < Math.abs(nearest - widthRatio) ? value : nearest, 1);
    if (window.top === window && Math.abs(window.outerWidth - innerWidth * step) <= 18
        && innerHeight * step <= window.outerHeight + 2) displayDensity = ratio / step;
    displayDensity ??= ratio;
    moduleZoom = ratio / displayDensity;
    moduleScale = fit * moduleZoom;
    previous = { ratio, outerWidth, outerHeight, zoom: browserZoom };
    restore();
    try { window.sessionStorage.setItem(storageKey, JSON.stringify(previous)); } catch {}
  };
  update();
  // React can reconcile the root attributes after a login server action.
  // Restore only our properties, in the mutation microtask before paint;
  // otherwise the canvas falls back to its full 1920 x 1080 size until resize.
  new MutationObserver(restore).observe(root, { attributes: true, attributeFilter: ['style'] });
  window.addEventListener('resize', update);
  document.addEventListener('fullscreenchange', update);
})();`;
