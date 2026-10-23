import { readFile } from "node:fs/promises";
import path from "node:path";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

const notices: Record<string, string> = {
  FORBIDDEN: "当前飞书账号尚未获得管理权限，请联系超级管理员授权后再登录。",
  IDENTITY_NOT_LINKED: "当前飞书账号尚未获得管理权限，请联系超级管理员授权后再登录。",
  IDENTITY_REVOKED: "当前飞书账号的访问权限已撤销，请联系超级管理员。",
  SESSION_EXPIRED: "登录已失效，请重新使用飞书进入。",
  OAUTH_STATE_EXPIRED: "本次登录已超时，请重新使用飞书进入。",
  OAUTH_STATE_REPLAY: "本次登录链接已使用，请重新使用飞书进入。",
  IDENTITY_PROVIDER_UNAVAILABLE: "飞书登录暂时不可用，请稍后重新尝试。",
  IDENTITY_LOGIN_FAILED: "登录未完成，请重新使用飞书进入。",
};

export async function GET(request: Request) {
  const error = new URL(request.url).searchParams.get("auth_error") ?? "";
  const notice = Object.hasOwn(notices, error) ? notices[error] : "";
  const nonce = ((await headers()).get("x-nonce") ?? "").replace(/[^a-zA-Z0-9+/=]/g, "");
  const source = await readFile(path.join(process.cwd(), "public/review-native/feishu-login.html"), "utf8");
  const html = source.replace("<!--AUTH_NOTICE-->", notice)
    .replace(/<script\b/g, `<script nonce="${nonce}"`);
  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}
