// Resolve the saved appearance before loading styles to avoid a light flash.
(() => {
  let theme;
  try { theme = localStorage.getItem('journey_admin_theme'); } catch {}
  if (theme !== 'light' && theme !== 'dark') {
    theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#151617' : '#f7f7f7';
})();
