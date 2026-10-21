import { readFile } from "node:fs/promises";
import path from "node:path";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

const notices: Record<string, string> = {
  FORBIDDEN: "当前账号没有审核权限，请使用已授权的飞书账号进入。",
  SESSION_EXPIRED: "登录已失效，请重新使用飞书进入。",
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
