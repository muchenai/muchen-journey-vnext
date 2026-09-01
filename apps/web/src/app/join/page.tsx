import { cookies } from "next/headers";

import { confirmIdentity } from "@/app/actions";

import { InviteTokenExchangeForm } from "./invite-token-exchange-form";
import { JoinSubmitButton } from "./join-submit-button";
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
  searchParams: Promise<{ code?: string; request_id?: string }>;
}) {
  const query = await searchParams;
  const cookieStore = await cookies();
  const summary = parseSummary(cookieStore.get("journey_next_join_summary")?.value);
  const errorMessage = query.code ? ERROR_MESSAGES[query.code] ?? "邀请处理失败，请联系运营。" : null;
  const isReentry = summary?.flow === "REENTRY";
  const orientationDescriptionId = "join-whole-journey-next-action";
  const orientationPhase: OrientationPhase = summary
    ? isReentry
      ? "REENTRY"
      : "CONFIRM_IDENTITY"
    : "VERIFY_INVITE";

  return (
    <section className="learner-join">
      <div className="join-intro">
        <p className="journey-whisper">{isReentry ? "Welcome back." : "Private invitation · Map 01"}</p>
        <h1>{isReentry ? "回到你离开的地方。" : "你的探索营，已经在等你。"}</h1>
        <PrivateInviteOrientation phase={orientationPhase} descriptionId={orientationDescriptionId} />
      </div>
      <div className="join-action-card">
        <div className="join-action-heading">
          <span>现在只做一件事</span>
          <strong>{summary ? "确认身份，进入第一站" : "验证你的专属邀请"}</strong>
        </div>
        {errorMessage ? (
          <div className="notice" role="alert">
            <strong>{errorMessage}</strong>
            {query.request_id ? <p>请求编号：{query.request_id}</p> : null}
          </div>
        ) : null}
        {summary ? (
          <article className="join-pass">
            <span className="join-pass-label">邀请用途</span>
            <h2>{summary.purpose}</h2>
            <time dateTime={summary.expires_at}>
              有效至 {new Date(summary.expires_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
            </time>
            <form action={confirmIdentity} aria-describedby={orientationDescriptionId}>
              {!isReentry ? (
                <>
                  <label htmlFor="display-name">旅程中怎么称呼你？</label>
                  <input id="display-name" name="display_name" minLength={1} maxLength={120} required />
                </>
              ) : (
                <p className="status-meta">从上次离开的地方继续，回到旅程；原有进度会被安全恢复，不会创建重复记录。</p>
              )}
              <label className="consent-row">
                <input type="checkbox" name="accepted_purpose" value="yes" required />
                我确认这是我的邀请
              </label>
              <JoinSubmitButton
                idleLabel={isReentry ? "继续当前一站" : "进入探索营"}
                pendingLabel={isReentry ? "正在恢复…" : "正在开启…"}
              />
            </form>
          </article>
        ) : (
          <InviteTokenExchangeForm orientationDescriptionId={orientationDescriptionId} />
        )}
      </div>
    </section>
  );
}
