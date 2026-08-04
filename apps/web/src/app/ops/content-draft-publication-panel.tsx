import { publishContentDraft } from "@/app/actions";
import type {
  ContentDraft,
  OpsIdentityAccess,
  OpsTaskDefinition,
} from "@/lib/server/api";

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
              <label className="checkbox-row">
                <input type="checkbox" name="review_acknowledged" required />
                我确认 Reviewer 已复核材料来源、任务边界和 Rubric；发布后正文不可原地修改
              </label>
              <button className="button primary compact" type="submit">发布精确快照</button>
            </form>
          </li>
        );
      })}
    </ul>
  );
}
