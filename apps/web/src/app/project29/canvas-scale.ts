// Run synchronously in <head>, before any learner canvas can be painted.
// A CSS variable keeps SSR, hydration and subsequent page mounts at one scale.
export const canvasScaleBootstrap = `(() => {
  const root = document.documentElement;
  const storageKey = 'journey.canvas.viewport.v1';
  let previous = null;
  let browserZoom = 1;
  let scale = 1;
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(storageKey) || 'null');
    if (saved && [saved.ratio, saved.outerWidth, saved.outerHeight, saved.zoom].every(Number.isFinite)
        && saved.ratio > 0 && saved.zoom >= 0.1 && saved.zoom <= 10) {
      previous = saved;
      browserZoom = saved.zoom;
    }
  } catch {}
  const restore = () => {
    const value = String(scale);
    if (root.style.getPropertyValue('--journey-canvas-scale') !== value) {
      root.style.setProperty('--journey-canvas-scale', value);
    }
    const overflow = browserZoom > 1.001 ? 'auto' : 'hidden';
    if (root.style.getPropertyValue('--journey-canvas-overflow') !== overflow) {
      root.style.setProperty('--journey-canvas-overflow', overflow);
    }
  };
  const update = () => {
    const ratio = window.devicePixelRatio || 1;
    const outerWidth = window.outerWidth || window.innerWidth;
    const outerHeight = window.outerHeight || window.innerHeight;
    // Browser zoom changes CSS viewport dimensions and DPR while the window
    // stays the same size. Do not cancel the user's zoom by fitting again.
    if (previous && Math.abs(outerWidth - previous.outerWidth) <= 2
        && Math.abs(outerHeight - previous.outerHeight) <= 2) {
      browserZoom = Math.max(0.1, Math.min(10, browserZoom * ratio / previous.ratio));
    }
    scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080) * browserZoom;
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
