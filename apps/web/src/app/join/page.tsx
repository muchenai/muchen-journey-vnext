import { cookies } from "next/headers";

import { confirmIdentity } from "@/app/actions";

import { InviteTokenExchangeForm } from "./invite-token-exchange-form";

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

  return (
    <section className="learner-join">
      <div className="join-scene" aria-hidden="true">
        <div className="join-scene-copy">
          <span>DAY 0 · 启程</span>
          <strong>第一站已经为你亮起</strong>
          <small>一天 · 八站 · 一段由你完成的旅程</small>
        </div>
        <ol>
          {Array.from({ length: 8 }, (_, index) => <li key={index} />)}
        </ol>
      </div>
      <div className="join-entry">
        <p className="journey-whisper">{isReentry ? "Welcome back." : "Your journey starts here."}</p>
        <h1>{isReentry ? "回到你离开的地方。" : "这张通行证，只属于你。"}</h1>
        <p className="join-promise">从 Day 0 出发，找到四枚宝藏，完成三次真实判断。</p>
        {errorMessage ? (
          <div className="notice" role="alert">
            <strong>{errorMessage}</strong>
            {query.request_id ? <p>请求编号：{query.request_id}</p> : null}
          </div>
        ) : null}
        {summary ? (
          <article className="join-pass">
            <span className="join-pass-label">Muchen Journey · 邀请</span>
            <h2>{summary.purpose}</h2>
            <time dateTime={summary.expires_at}>
              {new Date(summary.expires_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
            </time>
            <form action={confirmIdentity}>
              {!isReentry ? (
                <>
                  <label htmlFor="display-name">旅途中怎么称呼你</label>
                  <input id="display-name" name="display_name" minLength={1} maxLength={120} required />
                </>
              ) : (
                <p className="status-meta">从上次离开的地方继续。</p>
              )}
              <label className="consent-row">
                <input type="checkbox" name="accepted_purpose" value="yes" required />
                我确认这是我的邀请
              </label>
              <button className="button primary" type="submit">
                {isReentry ? "回到旅程" : "走进第一站"}
              </button>
            </form>
          </article>
        ) : (
          <InviteTokenExchangeForm />
        )}
      </div>
    </section>
  );
}
