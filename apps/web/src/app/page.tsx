import Link from "next/link";

const AUTH_ERRORS: Record<string, string> = {
  IDENTITY_NOT_LINKED: "该飞书身份尚未获得访问权限，请联系运营获取一次性绑定链接。",
  IDENTITY_REVOKED: "该飞书身份已撤销，请联系运营确认权限。",
  IDENTITY_PROVIDER_DISABLED: "飞书登录尚未完成环境配置。",
  IDENTITY_PROVIDER_UNAVAILABLE: "飞书登录暂时不可用，请稍后重新开始。",
  SESSION_EXPIRED: "当前会话已失效。业务事实未受影响；如仍有权限，请重新使用飞书登录。",
  LEARNER_SESSION_EXPIRED: "新人会话已失效。已提交的任务与评审事实仍然保留；请联系试点运营获取一次性重新进入链接。",
};

const IDENTITY_RETURN_PATHS = new Set(["/review", "/ops"]);

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ auth_error?: string; return_to?: string }>;
}) {
  const query = await searchParams;
  const authError = query.auth_error;
  const returnTo = query.return_to && IDENTITY_RETURN_PATHS.has(query.return_to)
    ? query.return_to
    : null;
  return (
    <section className="hero product-home">
      <p className="eyebrow">从行动开始</p>
      <h1>把一个真实问题，变成清晰的下一步。</h1>
      <p className="lede">
        围绕你正在面对的问题，完成一次行动、获得具体反馈，然后继续前进。
      </p>
      <div className="action-row">
        <Link className="button primary" href="/app">
          继续我的行动
        </Link>
      </div>
      {authError ? (
        <div className="inline-error" role="alert">
          <p>{AUTH_ERRORS[authError] ?? "身份登录没有完成，请重新开始或联系运营。"}</p>
          {authError === "SESSION_EXPIRED" && returnTo ? (
            <Link href={`/auth/feishu?return_to=${encodeURIComponent(returnTo)}`}>
              重新使用飞书登录
            </Link>
          ) : null}
        </div>
      ) : null}
      <section className="journey-intro" aria-labelledby="journey-intro-title">
        <h2 id="journey-intro-title">一次只走好一步</h2>
        <ol className="journey-steps">
          <li>
            <strong>看清当前任务</strong>
            <span>知道现在要解决什么，以及完成的标准。</span>
          </li>
          <li>
            <strong>提交真实成果</strong>
            <span>用自己的工作内容回应问题，而不是完成形式。</span>
          </li>
          <li>
            <strong>带着反馈继续</strong>
            <span>获得具体建议，明确下一步行动。</span>
          </li>
        </ol>
      </section>
      <p className="role-entry">
        首次加入请打开运营同学发送的专属邀请链接。主管可从
        <Link href="/auth/feishu?return_to=%2Freview">评审入口</Link>
        登录。
      </p>
    </section>
  );
}
