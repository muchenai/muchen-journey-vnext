const SESSION_KEY = 'journey_admin_invite_session_v1';
const SESSION_DURATION = 7 * 24 * 60 * 60 * 1000;
let currentSession = null;

// Temporary prototype entry. Replace this local gate with a server session for real authentication.
function activeInviteSession() {
  let session = currentSession;
  try { session = JSON.parse(localStorage.getItem(SESSION_KEY)) || session; } catch {}
  return [1, 2].includes(session?.version) && Number(session.expiresAt) > Date.now() ? session : null;
}

export function isInviteLoggedIn() {
  return Boolean(activeInviteSession());
}

export function getCurrentInviteUser() {
  const session = activeInviteSession();
  if (!session) return null;
  // Legacy v1 sessions came exclusively from the same AAA administrator invitation.
  const accessRole = session.accessRole === 'super_admin' || (session.version === 1 && !session.accessRole) ? 'super_admin' : session.accessRole === 'admin' ? 'admin' : 'member';
  return { id: session.userId || (accessRole === 'super_admin' ? 'preview-super-admin' : 'preview-member'), name: session.name || '林老师', accessRole };
}

export function clearInviteSession() {
  currentSession = null;
  try { localStorage.removeItem(SESSION_KEY); } catch {}
}

export function renderInviteLogin(themeContent, dark) {
  return `<main class="login-page">
    <header class="login-header"><a href="#" class="login-brand" aria-label="JOURNEY 管理系统"><img src="./journey-logo-119.svg" alt="" width="34" height="34"><span>JOURNEY<small>管理系统</small></span></a><button class="theme-toggle" id="theme-toggle" type="button" aria-label="切换为${dark ? '浅色' : '深色'}模式">${themeContent}</button></header>
    <section class="login-card" aria-labelledby="login-title">
      <div class="login-symbol"><img src="./journey-logo-119.svg" alt="" width="48" height="48"></div>
      <h1 id="login-title">登录管理系统</h1>
      <p class="login-intro">使用邀请码进入 JOURNEY</p>
      <form id="invite-login-form" novalidate>
        <label class="login-field" for="invite-code">邀请码</label>
        <input id="invite-code" name="inviteCode" type="text" placeholder="请输入邀请码" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="32" aria-required="true" aria-describedby="invite-login-error">
        <p class="login-error" id="invite-login-error" role="status" aria-live="polite"></p>
        <button class="btn btn-primary login-submit" type="submit">登录</button>
      </form>
      <p class="login-note">仅限受邀导师与管理员</p>
    </section>
    <footer class="login-footer">JOURNEY 管理系统</footer>
  </main>`;
}

export function bindInviteLogin({ onLogin, onThemeToggle }) {
  const form = document.getElementById('invite-login-form');
  const input = document.getElementById('invite-code');
  const error = document.getElementById('invite-login-error');
  document.getElementById('theme-toggle').onclick = onThemeToggle;
  document.querySelector('.login-brand').onclick = event => event.preventDefault();
  input.addEventListener('input', () => {
    error.textContent = '';
    input.removeAttribute('aria-invalid');
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    const code = input.value.trim().toUpperCase();
    if (code !== 'AAA') {
      error.textContent = code ? '邀请码不正确，请重新输入' : '请输入邀请码';
      input.setAttribute('aria-invalid', 'true');
      input.focus();
      return;
    }
    currentSession = { version: 2, userId: 'preview-super-admin', name: '林老师', accessRole: 'super_admin', expiresAt: Date.now() + SESSION_DURATION };
    try { localStorage.setItem(SESSION_KEY, JSON.stringify(currentSession)); } catch {}
    onLogin();
  });
}

export function onInviteSessionChange(callback) {
  window.addEventListener('storage', event => {
    if (event.key === SESSION_KEY || event.key === null) {
      currentSession = null;
      callback();
    }
  });
}
