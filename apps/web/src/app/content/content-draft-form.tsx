import type { ContentDraft, OpsTaskDefinition, TaskContentInput } from "@/lib/server/api";

type DraftFormProps = {
  action: (data: FormData) => Promise<void>;
  definitions?: OpsTaskDefinition[];
  draft?: ContentDraft;
};

const EMPTY: TaskContentInput = {
  title: "",
  purpose: "",
  learner_outcome: "",
  instructions: [],
  completion_criteria: [],
  required_deliverables: [],
  content_source_notes: [],
  change_summary: "",
  reviewer_calibration_note: "",
  allowed_attachment_types: [],
  max_attachment_size_bytes: 0,
  reference_materials: [],
  learning_materials: [],
  estimated_duration_minutes: 60,
  rubric: { version: 1, dimensions: [] },
  reviewer_role: "REVIEWER",
  feedback_sla_business_days: 2,
  sensitivity: "INTERNAL",
  audience: "LEARNER",
};

export function ContentDraftForm({ action, definitions, draft }: DraftFormProps) {
  const content = draft?.content ?? EMPTY;
  const textMaterial = content.learning_materials.find((item) => item.kind === "TEXT");
  const linkMaterial = content.learning_materials.find((item) => item.kind === "HTTPS_LINK");
  const rubric = content.rubric.dimensions[0];
  return (
    <form action={action} className="content-editor-form">
      {draft ? (
        <>
          <input type="hidden" name="draft_id" value={draft.id} />
          <input type="hidden" name="revision" value={draft.revision} />
        </>
      ) : (
        <label>
          固定任务
          <select name="task_definition_id" required defaultValue="">
            <option value="" disabled>选择任务定义</option>
            {(definitions ?? []).map((definition) => (
              <option key={definition.id} value={definition.id}>
                {definition.stable_key} · revision {definition.revision}
              </option>
            ))}
          </select>
        </label>
      )}

      <fieldset>
        <legend>这一站</legend>
        <label>标题<input name="title" required minLength={3} maxLength={180} defaultValue={content.title} /></label>
        <label>为什么学习<textarea name="purpose" required minLength={10} maxLength={2000} defaultValue={content.purpose} /></label>
        <label>完成后能够<textarea name="learner_outcome" required minLength={10} maxLength={2000} defaultValue={content.learner_outcome} /></label>
        <label>预计总时长（分钟）<input name="estimated_duration_minutes" type="number" min={1} max={480} defaultValue={content.estimated_duration_minutes} /></label>
      </fieldset>

      <fieldset>
        <legend>必读材料</legend>
        <div className="content-editor-grid">
          <label>稳定编号<input name="material_key" required pattern="[a-z0-9][a-z0-9_-]{2,79}" defaultValue={textMaterial?.key ?? ""} /></label>
          <label>标题<input name="material_title" required minLength={2} maxLength={160} defaultValue={textMaterial?.title ?? ""} /></label>
          <label>来源<input name="material_source" required minLength={2} maxLength={160} defaultValue={textMaterial?.source_label ?? ""} /></label>
          <label>时长（分钟）<input name="material_duration" type="number" min={1} max={120} defaultValue={textMaterial?.estimated_duration_minutes ?? 10} /></label>
        </div>
        <label>材料正文<textarea name="material_body" required minLength={20} maxLength={20000} rows={12} defaultValue={textMaterial?.body ?? ""} /></label>
      </fieldset>

      <fieldset>
        <legend>可选外部 HTTPS 材料</legend>
        <div className="content-editor-grid">
          <label>稳定编号<input name="link_key" pattern="[a-z0-9][a-z0-9_-]{2,79}" defaultValue={linkMaterial?.key ?? "external-source"} /></label>
          <label>标题<input name="link_title" minLength={2} maxLength={160} defaultValue={linkMaterial?.title ?? "外部参考材料"} /></label>
          <label>来源<input name="link_source" minLength={2} maxLength={160} defaultValue={linkMaterial?.source_label ?? "来源待填写"} /></label>
          <label>时长（分钟）<input name="link_duration" type="number" min={1} max={120} defaultValue={linkMaterial?.estimated_duration_minutes ?? 10} /></label>
        </div>
        <label>URL<input name="link_url" type="url" pattern="https://.*" defaultValue={linkMaterial?.url ?? ""} /></label>
      </fieldset>

      <fieldset>
        <legend>主题小任务</legend>
        <label>步骤（每行一条）<textarea name="instructions" required defaultValue={content.instructions.join("\n")} /></label>
        <label>完成标准（每行一条）<textarea name="completion_criteria" required defaultValue={content.completion_criteria.join("\n")} /></label>
        <label>交付物（每行一条）<textarea name="required_deliverables" required defaultValue={content.required_deliverables.join("\n")} /></label>
        <label>
          提交后开放的参考答案（每行一条，可留空）
          <textarea
            name="reference_materials"
            placeholder="参考答案：https://…"
            defaultValue={content.reference_materials.join("\n")}
          />
        </label>
      </fieldset>

      <fieldset>
        <legend>Reviewer 标尺</legend>
        <div className="content-editor-grid">
          <label>维度标题<input name="rubric_title" required defaultValue={rubric?.title ?? "证据可定位"} /></label>
          <label>反馈时限（工作日）<input name="feedback_sla_business_days" type="number" min={1} max={10} defaultValue={content.feedback_sla_business_days} /></label>
        </div>
        <label>维度目的<textarea name="rubric_purpose" required defaultValue={rubric?.purpose ?? ""} /></label>
        <label>期望证据<textarea name="rubric_evidence" required defaultValue={rubric?.evidence_expected ?? ""} /></label>
        <label>达到要求<textarea name="rubric_meets" required defaultValue={rubric?.levels.MEETS ?? ""} /></label>
        <label>需要修订<textarea name="rubric_needs_work" required defaultValue={rubric?.levels.NEEDS_WORK ?? ""} /></label>
        <label>反馈提示<textarea name="rubric_feedback_prompt" required defaultValue={rubric?.feedback_prompt ?? ""} /></label>
      </fieldset>

      <fieldset>
        <legend>来源与复核</legend>
        <label>内容来源（每行一条）<textarea name="content_source_notes" required defaultValue={content.content_source_notes.join("\n")} /></label>
        <label>本次变化<textarea name="change_summary" required defaultValue={content.change_summary} /></label>
        <label>Reviewer 校准说明<textarea name="reviewer_calibration_note" required defaultValue={content.reviewer_calibration_note} /></label>
      </fieldset>

      <button className="button primary" type="submit">
        {draft ? "保存草稿" : "创建草稿"}
      </button>
    </form>
  );
}
