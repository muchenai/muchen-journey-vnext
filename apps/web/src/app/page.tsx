import Link from "next/link";

const AUTH_ERRORS: Record<string, string> = {
  IDENTITY_NOT_LINKED: "该飞书身份尚未获得访问权限，请联系运营获取一次性绑定链接。",
  IDENTITY_REVOKED: "该飞书身份已撤销，请联系运营确认权限。",
  IDENTITY_PROVIDER_DISABLED: "飞书登录尚未完成环境配置。",
  IDENTITY_PROVIDER_UNAVAILABLE: "飞书登录暂时不可用，请稍后重新开始。",
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ auth_error?: string }>;
}) {
  const authError = (await searchParams).auth_error;
  return (
    <section className="hero">
      <p className="eyebrow">探索营 · P0</p>
      <h1>只看一个当前行动，完成一次真实闭环。</h1>
      <p className="lede">
        新人提交真实成果，主管评审固定版本，系统保留事实并给出唯一下一步。
      </p>
      <div className="action-row">
        <Link className="button primary" href="/join">
          使用邀请加入
        </Link>
        <Link className="button secondary" href="/app">
          已加入，进入当前行动
        </Link>
        <Link className="button secondary" href="/auth/feishu?return_to=%2Freview">
          飞书登录进入主管评审
        </Link>
        <Link className="button secondary" href="/auth/feishu?return_to=%2Fops">
          飞书登录进入运营
        </Link>
      </div>
      {authError ? (
        <p className="inline-error" role="alert">
          {AUTH_ERRORS[authError] ?? "身份登录没有完成，请重新开始或联系运营。"}
        </p>
      ) : null}
      <aside className="notice" aria-label="环境说明">
        Alpha 试点仅限受邀参与者。新人使用邀请加入；主管和运营使用飞书登录。
        如无法进入，请联系试点运营。
      </aside>
    </section>
  );
}
