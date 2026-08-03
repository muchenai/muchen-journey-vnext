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
const ROUTE_PREVIEW = [
  ["启程", "带着一个问题出发"],
  ["价值", "看见你愿意成为谁"],
  ["模型", "理解判断为何会出错"],
  ["项目", "把答案放回真实场景"],
  ["交付", "分清判断与提报边界"],
  ["规则", "拆出目标、维度与红线"],
  ["判断", "用证据比较模型回答"],
  ["边界", "在不确定中做谨慎判断"],
] as const;

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
    <section className="learner-landing">
      <div className="landing-copy">
        <p className="journey-whisper">It&apos;s a long game.</p>
        <h1>这里，没有标准答案。</h1>
        <Link className="button primary landing-cta" href="/app">
          继续旅程 <span aria-hidden="true">→</span>
        </Link>
      </div>
      <ol className="landing-route" aria-label="探索营路线预览">
        {ROUTE_PREVIEW.map(([title, hint], index) => (
          <li key={title}>
            <span
              className="landing-route-node"
              data-hint={`${title} · ${hint}`}
              tabIndex={0}
              aria-label={`第 ${index + 1} 站：${title}。${hint}`}
            >
              <i aria-hidden="true" />
            </span>
          </li>
        ))}
      </ol>
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
      <p className="landing-footnote">
        首次进入使用专属邀请 · <Link href="/auth/feishu?return_to=%2Freview">Reviewer</Link>
      </p>
    </section>
  );
}
