import Link from "next/link";

export const dynamic = "force-dynamic";

export default function ContentLoginPage() {
  return (
    <main className="content-editor-page">
      <section
        className="panel content-editor-section"
        aria-labelledby="content-login-title"
      >
        <p className="eyebrow">Content Editor</p>
        <h1 id="content-login-title">进入内容工作台</h1>
        <p className="lede">使用已绑定的飞书身份继续。</p>
        <div>
          <Link className="button primary" href="/auth/feishu?return_to=%2Fcontent">
            使用飞书进入
          </Link>
        </div>
      </section>
    </main>
  );
}
