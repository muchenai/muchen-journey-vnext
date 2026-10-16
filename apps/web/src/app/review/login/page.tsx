import Link from "next/link";

export const dynamic = "force-dynamic";

const notices: Record<string, string> = {
  FORBIDDEN: "当前会话不是 Reviewer，请使用已授权的 Reviewer 飞书身份进入。",
  SESSION_EXPIRED: "Reviewer 会话已失效，请重新使用飞书进入。",
};

export default async function ReviewLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ auth_error?: string }>;
}) {
  const query = await searchParams;
  const notice = query.auth_error ? notices[query.auth_error] : undefined;
  const fixtureIdentityAllowed =
    process.env.APP_ENV === "local" &&
    process.env.ALLOW_FIXTURE_IDENTITY === "true";
  return (
    <main className="content-editor-page">
      <section className="panel content-editor-section" aria-labelledby="review-login-title">
        <p className="eyebrow">Reviewer</p>
        <h1 id="review-login-title">进入主管评审</h1>
        <p className="lede">
          {fixtureIdentityAllowed
            ? "使用本地测试 Reviewer 身份进入审核工作台。"
            : "使用已绑定且具备 Reviewer 权限的飞书身份继续。"}
        </p>
        {notice ? <p className="notice" role="status">{notice}</p> : null}
        <div>
          {fixtureIdentityAllowed ? (
            <Link className="button primary" href="/review/local">
              使用本地审核身份进入
            </Link>
          ) : (
            <Link className="button primary" href="/auth/feishu?return_to=%2Freview">
              使用飞书进入
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
