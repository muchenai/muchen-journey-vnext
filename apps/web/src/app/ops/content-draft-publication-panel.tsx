import { publishContentDraft } from "@/app/actions";
import type {
  ContentDraft,
  OpsIdentityAccess,
  OpsTaskDefinition,
} from "@/lib/server/api";

const HTTPS_URL = /https:\/\/[^\s<>"']+/gu;
const TRAILING_URL_PUNCTUATION = /[),.;!?，。；！？、）】》]+$/u;

function reviewableMaterialLinks(draft: ContentDraft) {
  const links = draft.content.learning_materials.flatMap((material) => {
    if (material.kind === "HTTPS_LINK" && material.url) {
      return [{ title: material.title, href: material.url }];
    }
    if (material.kind !== "TEXT" || !material.body) return [];
    return [...material.body.matchAll(HTTPS_URL)].map((match, index) => ({
      title: `${material.title} · 链接 ${index + 1}`,
      href: match[0].replace(TRAILING_URL_PUNCTUATION, ""),
    }));
  });
  return links.filter(
    (link, index) => links.findIndex((candidate) => candidate.href === link.href) === index,
  );
}

export function ContentDraftPublicationPanel({
  drafts,
  definitions,
  reviewers,
}: {
  drafts: ContentDraft[];
  definitions: OpsTaskDefinition[];
  reviewers: OpsIdentityAccess[];
}) {
  if (drafts.length === 0) return <p>当前没有等待发布的内容草稿。</p>;
  if (reviewers.length === 0) {
    return <p className="inline-error">没有已绑定的 Reviewer，不能把复核确认伪造成完成。</p>;
  }
  return (
    <ul className="ops-list">
      {drafts.map((draft) => {
        const definition = definitions.find((item) => item.id === draft.task_definition_id);
        if (!definition) return null;
        const materialLinks = reviewableMaterialLinks(draft);
        return (
          <li key={draft.id} className="ops-enrollment">
            <div>
              <strong>{draft.content.title}</strong>
              <span>{draft.stable_key} · draft revision {draft.revision} · {draft.content.learning_materials.length} 份材料</span>
            </div>
            <form action={publishContentDraft} className="ops-command-form">
              <input type="hidden" name="draft_id" value={draft.id} />
              <input type="hidden" name="revision" value={draft.revision} />
              <input type="hidden" name="definition_revision" value={definition.revision} />
              <label>
                独立 Reviewer
                <select name="reviewer_id" required defaultValue="">
                  <option value="" disabled>选择完成线下复核的人</option>
                  {reviewers.map((reviewer) => (
                    <option key={reviewer.user_id} value={reviewer.user_id}>
                      {reviewer.display_name}
                    </option>
                  ))}
                </select>
              </label>
              {materialLinks.length > 0 ? (
                <fieldset className="content-link-review">
                  <legend>逐项打开材料链接</legend>
                  <p className="status-meta">
                    必须在当前浏览器实际打开并确认可访问；只看 URL 文本不算完成。
                  </p>
                  {materialLinks.map((link, index) => (
                    <label className="checkbox-row" key={link.href}>
                      <input
                        name={`material_link_verified_${index}`}
                        type="checkbox"
                        required
                      />
                      <a href={link.href} target="_blank" rel="noreferrer">
                        {link.title} · {new URL(link.href).hostname}
                      </a>
                    </label>
                  ))}
                </fieldset>
              ) : null}
              <label className="checkbox-row">
                <input type="checkbox" name="review_acknowledged" required />
                我确认 Reviewer 已复核材料来源、任务边界和 Rubric，且上列链接均已实际打开；发布后正文不可原地修改
              </label>
              <button className="button primary compact" type="submit">发布精确快照</button>
            </form>
          </li>
        );
      })}
    </ul>
  );
}
