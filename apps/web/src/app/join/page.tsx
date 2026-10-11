import { cookies } from "next/headers";

import ProjectExperience from "@/app/project9/App";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  IDENTITY_PROVIDER_DISABLED: "飞书登录尚未配置，请联系管理员完成应用配置。",
  LEARNER_LOGIN_NOT_CONFIGURED: "默认学习旅程或审核人尚未配置，请联系管理员。",
  IDENTITY_PROVIDER_UNAVAILABLE: "飞书授权未能完成，请重新登录；如仍失败，请联系管理员检查应用配置。",
  IDENTITY_REVOKED: "该飞书身份已停用，请联系管理员。",
  OAUTH_BROWSER_MISMATCH: "登录已过期或登录地址发生变化，请从当前页面重新登录。",
  OAUTH_STATE_REPLAY: "这次授权已使用，请重新点击飞书登录。",
  OAUTH_STATE_EXPIRED: "授权已过期，请重新点击飞书登录。",
  OAUTH_CALLBACK_INVALID: "飞书授权未完成，请重新登录。",
  INVITE_EXPIRED_OR_REVOKED: "邀请无效、已过期、已撤销或已经使用，请重新获取邀请码。",
  FORBIDDEN: "该身份没有加入权限，请联系运营。",
  INVALID_STATE_TRANSITION: "该身份已有进行中的加入记录，请联系运营处理。",
  RATE_LIMITED: "验证次数过多，请稍后再试。",
  VALIDATION_FAILED: "请输入 1–120 个字符的昵称。",
  PURPOSE_NOT_ACCEPTED: "确认邀请用途后才能继续。",
};

type JoinSummary = { flow: "JOIN" | "REENTRY"; purpose: string; expires_at: string };

function parseSummary(value: string | undefined): JoinSummary | null {
  if (!value) return null;
  try {
    return JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as JoinSummary;
  } catch {
    return null;
  }
}

export default async function JoinPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string; auth_error?: string; method?: string }>;
}) {
  const [query, cookieStore] = await Promise.all([searchParams, cookies()]);
  const summary = parseSummary(cookieStore.get("journey_next_join_summary")?.value);
  return (
    <ProjectExperience
      initialScreen="login"
      joinPhase={query.method === "invite" ? (summary ? "identity" : "invite") : "feishu"}
      joinError={query.auth_error ? ERRORS[query.auth_error] ?? "飞书登录失败，请重新尝试。" : query.code ? ERRORS[query.code] ?? "登录处理失败，请重试。" : ""}
    />
  );
}
