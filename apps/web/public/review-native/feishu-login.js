// Use the designer's workspace theme without loading its prototype sign-in.
(() => {
  const toggle = document.getElementById('theme-toggle');
  function applyTheme(theme, persist = false) {
    const dark = theme === 'dark';
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = dark ? '#151617' : '#f7f7f7';
    if (persist) { try { localStorage.setItem('journey_admin_theme', theme); } catch {} }
    const symbol = dark
      ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>'
      : '<path d="M20.8 13a8.8 8.8 0 0 1-9.8-9.8A9 9 0 1 0 20.8 13Z"/>';
    toggle.innerHTML = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${symbol}</svg><span>${dark ? '浅色' : '深色'}</span>`;
    toggle.setAttribute('aria-label', dark ? '切换为浅色模式' : '切换为深色模式');
    toggle.title = toggle.getAttribute('aria-label');
  }
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  toggle.onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
    let saved;
    try { saved = localStorage.getItem('journey_admin_theme'); } catch {}
    if (saved !== 'light' && saved !== 'dark') applyTheme(event.matches ? 'dark' : 'light');
  });
})();
