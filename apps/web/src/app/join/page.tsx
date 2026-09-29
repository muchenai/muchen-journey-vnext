import { cookies } from "next/headers";

import { confirmIdentity } from "@/app/actions";

import { InviteTokenExchangeForm } from "./invite-token-exchange-form";
import { JoinSubmitButton } from "./join-submit-button";
import { LanguageSwitcher, type JoinLocale } from "./language-switcher";
import { PrivateInviteOrientation, type OrientationPhase } from "./private-invite-orientation";

export const dynamic = "force-dynamic";

const ERROR_MESSAGES: Record<string, string> = {
  INVITE_EXPIRED_OR_REVOKED: "邀请无效、已过期、已撤销或已经使用。请联系运营重新获取。",
  FORBIDDEN: "受邀身份已停用或没有加入权限，请联系运营。",
  INVALID_STATE_TRANSITION: "该身份已有进行中的加入记录，请联系运营处理。",
  RATE_LIMITED: "邀请验证尝试过多，请稍后再试。",
  VALIDATION_FAILED: "请填写 1–120 个字符的称呼。",
  PURPOSE_NOT_ACCEPTED: "确认邀请用途后才能继续。",
};

const ERROR_MESSAGES_EN: Record<string, string> = {
  INVITE_EXPIRED_OR_REVOKED: "This invitation is invalid, expired, revoked, or already used. Contact Operations for a new one.",
  FORBIDDEN: "This identity is inactive or is not allowed to join. Contact Operations.",
  INVALID_STATE_TRANSITION: "This identity already has an active join request. Contact Operations.",
  RATE_LIMITED: "Too many verification attempts. Please try again later.",
  VALIDATION_FAILED: "Enter a display name between 1 and 120 characters.",
  PURPOSE_NOT_ACCEPTED: "Confirm the invitation purpose to continue.",
};

type JoinSummary = {
  flow: "JOIN" | "REENTRY";
  purpose: string;
  expires_at: string;
};

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
  searchParams: Promise<{ code?: string; request_id?: string; lang?: string }>;
}) {
  const query = await searchParams;
  const cookieStore = await cookies();
  const locale: JoinLocale = query.lang === "en" || cookieStore.get("journey_locale")?.value === "en" ? "en" : "zh-CN";
  const isEnglish = locale === "en";
  const summary = parseSummary(cookieStore.get("journey_next_join_summary")?.value);
  const errorMessage = query.code
    ? (isEnglish ? ERROR_MESSAGES_EN : ERROR_MESSAGES)[query.code]
      ?? (isEnglish ? "The invitation could not be processed. Contact Operations." : "邀请处理失败，请联系运营。")
    : null;
  const isReentry = summary?.flow === "REENTRY";
  const orientationDescriptionId = "join-whole-journey-next-action";
  const orientationPhase: OrientationPhase = summary
    ? isReentry
      ? "REENTRY"
      : "CONFIRM_IDENTITY"
    : "VERIFY_INVITE";

  return (
    <section className="learner-join" data-locale={locale}>
      <header className="join-topbar">
        <div className="join-brand-lockup">
          <img className="join-brand-mark" src="/images/muchen-journey-group5-orb.png" alt="" />
          <span><strong>MUCHEN JOURNEY</strong><small>{isEnglish ? "NEWCOMER VILLAGE" : "沐晨新手村"}</small></span>
        </div>
        <div className="join-top-actions">
          <LanguageSwitcher locale={locale} />
          <span className="join-help-center" aria-label={isEnglish ? "Help center" : "帮助中心"}>
            <span aria-hidden="true" className="join-language-icon">◎</span>{isEnglish ? "Help Center" : "帮助中心"}
          </span>
        </div>
      </header>
      <div className="join-intro">
        <h1>
          <span className="sr-only">你的探索营，已经在等你。</span>
          <span className="join-heading-visible">
          {isReentry
            ? (isEnglish ? "Return to where you left off." : "回到你离开的地方。")
            : (isEnglish ? "Muchen Journey | Newcomer Village" : "Muchen Journey | 沐晨新手村")}
          </span>
        </h1>
        <PrivateInviteOrientation phase={orientationPhase} descriptionId={orientationDescriptionId} locale={locale} />
        <p className="join-departure-line">
          {isEnglish ? <>A greater you<br />starts here</> : <>更大的你<br />从这里出发</>}
        </p>
      </div>
      <div className="join-action-card">
        <div className="join-card-brand" aria-hidden="true">
          <img className="join-brand-mark" src="/images/muchen-journey-group5-orb.png" alt="" />
          <strong>Muchen Journey</strong>
        </div>
        <div className="join-action-heading">
          <span>{isEnglish ? "YOUR JOURNEY STARTS HERE" : "从这里开启真实世界旅程"}</span>
          <strong>
            <span className="sr-only">验证你的专属邀请</span>
            {summary
              ? (isEnglish ? "Confirm your identity" : "确认身份，进入第一站")
              : (isEnglish ? "Welcome back to Newcomer Village" : "欢迎回到沐晨新手村")}
          </strong>
          <p>{isEnglish ? "Verify your invitation and continue exploring real-world AI work." : "验证专属邀请，继续探索真实业务世界"}</p>
        </div>
        {errorMessage ? (
          <div className="notice" role="alert">
            <strong>{errorMessage}</strong>
            {query.request_id ? <p>{isEnglish ? "Request ID" : "请求编号"}：{query.request_id}</p> : null}
          </div>
        ) : null}
        {summary ? (
          <article className="join-pass">
            <span className="join-pass-label">{isEnglish ? "INVITATION PURPOSE" : "邀请用途"}</span>
            <h2>{summary.purpose}</h2>
            <time dateTime={summary.expires_at}>
              {isEnglish ? "Valid until" : "有效至"} {new Date(summary.expires_at).toLocaleString(isEnglish ? "en-US" : "zh-CN", { timeZone: "Asia/Shanghai" })}
            </time>
            <form action={confirmIdentity} aria-describedby={orientationDescriptionId}>
              {!isReentry ? (
                <>
                  <label htmlFor="display-name">{isEnglish ? "What should we call you?" : "旅程中怎么称呼你？"}</label>
                  <input id="display-name" name="display_name" minLength={1} maxLength={120} required />
                </>
              ) : (
                <p className="status-meta">
                  {isEnglish
                    ? "Continue from where you left off. Your progress will be restored without creating a duplicate record."
                    : "从上次离开的地方继续，回到旅程；原有进度会被安全恢复，不会创建重复记录。"}
                </p>
              )}
              <label className="consent-row">
                <input type="checkbox" name="accepted_purpose" value="yes" required />
                {isEnglish ? "I confirm this invitation is mine" : "我确认这是我的邀请"}
              </label>
              <JoinSubmitButton
                idleLabel={isEnglish ? (isReentry ? "Continue current stop" : "Enter Exploration Camp") : (isReentry ? "继续当前一站" : "进入探索营")}
                pendingLabel={isEnglish ? (isReentry ? "Restoring…" : "Opening…") : (isReentry ? "正在恢复…" : "正在开启…")}
              />
            </form>
          </article>
        ) : (
          <InviteTokenExchangeForm orientationDescriptionId={orientationDescriptionId} locale={locale} />
        )}
        <div className="join-auth-note">
          <span aria-hidden="true">◇</span>
          <p><strong>{isEnglish ? "Protected identity flow" : "受控身份验证"}</strong><small>{isEnglish ? "Invitation verification and enterprise identity protection" : "专属邀请验证与企业身份保护"}</small></p>
        </div>
      </div>
      <footer className="join-world-footer" aria-hidden="true">
        <span>{isEnglish ? "AI-powered growth · Connected to the real world" : "AI 驱动成长 · 连接真实世界"}</span>
        <span>{isEnglish ? "EXPLORE · PRACTICE · GROW · CREATE" : "探索 · 实践 · 成长 · 创造更大的价值"}</span>
      </footer>
    </section>
  );
}
