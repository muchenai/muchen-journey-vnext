import Link from "next/link";

import { createContentDraft, logoutSession } from "@/app/actions";
import { ContentDraftForm } from "@/app/content/content-draft-form";
import {
  ContentDraft,
  identityPageRequest,
  OpsTaskDefinition,
} from "@/lib/server/api";

export const dynamic = "force-dynamic";

export default async function ContentPage() {
  const [definitions, drafts] = await Promise.all([
    identityPageRequest<{ items: OpsTaskDefinition[] }>(
      "/api/v1/content/task-definitions",
      "CONTENT_EDITOR",
    ),
    identityPageRequest<{ items: ContentDraft[] }>(
      "/api/v1/content/drafts",
      "CONTENT_EDITOR",
    ),
  ]);
  return (
    <section className="content-editor-page">
      <header>
        <p className="eyebrow">Content Editor · 单宝藏</p>
        <h1>准备真实学习内容</h1>
        <p className="lede">草稿可改；提交复核后正文冻结；只有 Operator 能发布固定版本。</p>
      </header>

      <section className="panel content-editor-section">
        <h2>我的草稿</h2>
        {drafts.items.length === 0 ? <p>尚无草稿。</p> : null}
        <ul className="ops-list">
          {drafts.items.map((draft) => (
            <li key={draft.id}>
              <div>
                <strong>{draft.content.title}</strong>
                <span>{draft.stable_key} · {draft.status} · revision {draft.revision}</span>
              </div>
              <Link className="button secondary compact" href={`/content/drafts/${draft.id}`}>
                {draft.status === "DRAFT" ? "继续编辑" : "查看快照"}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel content-editor-section">
        <h2>新建单宝藏草稿</h2>
        {definitions.items.length > 0 ? (
          <ContentDraftForm action={createContentDraft} definitions={definitions.items} />
        ) : (
          <p className="inline-error">当前组织没有可编辑的任务定义；请让 Operator 先创建稳定编号。</p>
        )}
      </section>

      <form action={logoutSession}>
        <button className="button secondary" type="submit">退出内容会话</button>
      </form>
    </section>
  );
}
