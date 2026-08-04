import Link from "next/link";

import { submitContentDraft, updateContentDraft } from "@/app/actions";
import { ContentDraftForm } from "@/app/content/content-draft-form";
import { ContentDraft, identityPageRequest } from "@/lib/server/api";

export const dynamic = "force-dynamic";

export default async function ContentDraftPage({
  params,
  searchParams,
}: {
  params: Promise<{ draftId: string }>;
  searchParams: Promise<{ updated?: string }>;
}) {
  const [{ draftId }, query] = await Promise.all([params, searchParams]);
  const draft = await identityPageRequest<ContentDraft>(
    `/api/v1/content/drafts/${encodeURIComponent(draftId)}`,
    "CONTENT_EDITOR",
  );
  return (
    <section className="content-editor-page">
      <Link href="/content">← 返回草稿清单</Link>
      <header>
        <p className="eyebrow">{draft.stable_key} · {draft.status}</p>
        <h1>{draft.content.title}</h1>
        <p>revision {draft.revision}</p>
        {query.updated ? <p className="success-text" role="status">操作已保存。</p> : null}
      </header>

      {draft.status === "DRAFT" ? (
        <>
          <section className="panel content-editor-section">
            <h2>编辑与预览</h2>
            <ContentDraftForm action={updateContentDraft} draft={draft} />
          </section>
          <section className="panel content-editor-section">
            <h2>提交复核</h2>
            <p>提交后正文不可原地修改。若需更改，应创建新草稿。</p>
            <form action={submitContentDraft} className="ops-command-form">
              <input type="hidden" name="draft_id" value={draft.id} />
              <input type="hidden" name="revision" value={draft.revision} />
              <label>
                复核说明
                <textarea name="review_note" required minLength={10} maxLength={1000} />
              </label>
              <button className="button primary" type="submit">冻结正文并提交复核</button>
            </form>
          </section>
        </>
      ) : (
        <section className="panel content-editor-section">
          <h2>冻结快照</h2>
          <dl className="ops-facts">
            <div><dt>材料</dt><dd>{draft.content.learning_materials.length}</dd></div>
            <div><dt>任务步骤</dt><dd>{draft.content.instructions.length}</dd></div>
            <div><dt>状态</dt><dd>{draft.status}</dd></div>
            <div><dt>发布版本</dt><dd>{draft.published_task_version_id ?? "等待 Operator"}</dd></div>
          </dl>
          {draft.content.learning_materials.map((material) => (
            <article key={material.key} className="content-preview-card">
              <p className="eyebrow">{material.kind} · {material.source_label}</p>
              <h3>{material.title}</h3>
              {material.body ? <p>{material.body}</p> : <p>{material.url}</p>}
            </article>
          ))}
        </section>
      )}
    </section>
  );
}
