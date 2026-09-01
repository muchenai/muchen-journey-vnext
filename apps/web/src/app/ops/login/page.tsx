import Link from "next/link";

export const dynamic = "force-dynamic";

export default function OpsLoginPage() {
  return (
    <main className="content-editor-page">
      <section className="panel content-editor-section" aria-labelledby="ops-login-title">
        <p className="eyebrow">Operator</p>
        <h1 id="ops-login-title">进入运营工作台</h1>
        <p className="lede">使用已绑定且具备 Operator 权限的飞书身份继续。</p>
        <div>
          <Link className="button primary" href="/auth/feishu?return_to=%2Fops">
            使用飞书进入
          </Link>
        </div>
      </section>
    </main>
  );
}
