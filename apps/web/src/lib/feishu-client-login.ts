// Pinned official SDK, served with Journey so client login does not depend on
// a second network connection to a third-party CDN. See vendor/feishu/SOURCE.md.
const SDK_URL = "/vendor/feishu/h5-js-sdk-1.5.26.csp.js";
type Authorization = { code: string; state?: string };
type FeishuWindow = Window & {
  h5sdk?: { ready(callback: () => void): void; error(callback: () => void): void };
  tt?: { requestAccess(options: {
    appID: string; scopeList: string[]; state: string;
    success(result: Authorization): void; fail(result?: { errCode?: number; errno?: number }): void;
  }): void };
};

class ClientLoginError extends Error {
  constructor(readonly stage: string, readonly detail: string) { super(detail); }
}

async function atStage<T>(stage: string, action: () => Promise<T>): Promise<T> {
  try { return await action(); }
  catch (error) {
    const message = error instanceof Error ? error.message : "";
    // Never display raw SDK errors: they may contain authorization data.
    const detail = /^(?:SDK_[A-Z_]+|AUTH_[A-Z_]+(?::\d{1,12})?|OAUTH_[A-Z_]+|IDENTITY_[A-Z_]+|FORBIDDEN|VALIDATION_FAILED)$/.test(message)
      ? message : "UNAVAILABLE";
    throw new ClientLoginError(stage, detail);
  }
}

export function clientLoginErrorMessage(error: unknown): string {
  const labels: Record<string, string> = {
    sdk: "飞书登录组件加载失败", ready: "飞书客户端连接未就绪",
    start: "登录准备请求失败", authorize: "飞书客户端未完成授权", complete: "授权后的登录验证失败",
  };
  if (!(error instanceof ClientLoginError)) return "飞书登录未完成，请重新打开页面后重试。（诊断：unknown）";
  if (error.detail === "SDK_CONTAINER_UNAVAILABLE") {
    return "飞书登录组件未完成初始化，请反馈此诊断信息。（诊断：sdk/SDK_CONTAINER_UNAVAILABLE）";
  }
  return `${labels[error.stage]}。请将此提示反馈给管理员。（诊断：${error.stage}/${error.detail}）`;
}

export function isFeishuClient(userAgent: string): boolean {
  return /\b(?:Lark|Feishu)\//i.test(userAgent);
}

async function loadSdk(target: FeishuWindow): Promise<void> {
  if (target.h5sdk && target.tt?.requestAccess) return;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SDK_URL;
    script.async = true;
    const nonce = document.querySelector<HTMLScriptElement>("script[nonce]")?.nonce;
    if (nonce) script.nonce = nonce;
    const timer = window.setTimeout(() => { script.remove(); reject(new Error("SDK_TIMEOUT")); }, 15000);
    script.onload = () => { window.clearTimeout(timer); resolve(); };
    script.onerror = () => { window.clearTimeout(timer); script.remove(); reject(new Error("SDK_LOAD_FAILED")); };
    // Preserve the per-page CSP nonce; do not loosen the global script policy.
    document.head.appendChild(script);
  });
  if (!target.h5sdk || !target.tt?.requestAccess) throw new Error("SDK_CONTAINER_UNAVAILABLE");
}

async function clientRequest(body: Record<string, string>) {
  const response = await fetch("/auth/feishu/client", {
    method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Journey-Client-Login": "1" },
    body: JSON.stringify(body), signal: AbortSignal.timeout(15000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "LOGIN_FAILED");
  return data;
}

export async function loginInsideFeishu(): Promise<void> {
  const target = window as FeishuWindow;
  await atStage("sdk", () => loadSdk(target));
  await atStage("ready", () => new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("SDK_TIMEOUT")), 15000);
    target.h5sdk!.error(() => { window.clearTimeout(timer); reject(new Error("SDK_UNAVAILABLE")); });
    target.h5sdk!.ready(() => { window.clearTimeout(timer); resolve(); });
  }));
  const { appId, state } = await atStage("start", () => clientRequest({ step: "start" }));
  const authorization = await atStage("authorize", () => new Promise<Authorization>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("AUTH_TIMEOUT")), 90000);
    target.tt!.requestAccess({
      appID: appId, scopeList: [], state,
      success: (result) => { window.clearTimeout(timer); resolve(result); },
      fail: (error) => {
        window.clearTimeout(timer);
        const code = error?.errCode ?? error?.errno;
        reject(new Error(`AUTH_DENIED${typeof code === "number" && Number.isSafeInteger(code) && code >= 0 ? `:${code}` : ""}`));
      },
    });
  }));
  if (!authorization.code || (authorization.state && authorization.state !== state)) throw new ClientLoginError("authorize", "AUTH_INVALID");
  const result = await atStage("complete", () => clientRequest({ step: "complete", code: authorization.code, state }));
  if (result.entry !== "/app") throw new ClientLoginError("complete", "AUTH_INVALID");
  window.location.assign("/app");
}
