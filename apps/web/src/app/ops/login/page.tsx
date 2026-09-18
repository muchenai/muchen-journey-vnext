import Link from "next/link";

export const dynamic = "force-dynamic";

const notices: Record<string, string> = {
  FORBIDDEN: "当前会话没有 Operator 权限，请使用已授权的运营飞书身份进入。",
};

export default async function OpsLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ auth_error?: string }>;
}) {
  const query = await searchParams;
  const notice = query.auth_error ? notices[query.auth_error] : undefined;
  return (
    <main className="content-editor-page">
      <section className="panel content-editor-section" aria-labelledby="ops-login-title">
        <p className="eyebrow">Operator</p>
        <h1 id="ops-login-title">进入运营工作台</h1>
        <p className="lede">使用已绑定且具备 Operator 权限的飞书身份继续。</p>
        {notice ? <p className="notice" role="status">{notice}</p> : null}
        <div>
          <Link className="button primary" href="/auth/feishu?return_to=%2Fops">
            使用飞书进入
          </Link>
        </div>
      </section>
    </main>
  );
}
