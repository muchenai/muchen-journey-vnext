import { randomUUID } from "node:crypto";

import {
  completeLearningMaterial,
  deleteSubmissionAttachment,
  startAssignment,
} from "@/app/actions";
import { Assignment, learnerPageRequest } from "@/lib/server/api";
import { AttachmentUploader } from "./attachment-uploader";
import { SubmissionComposer } from "./submission-composer";

export const dynamic = "force-dynamic";

export default async function TaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{ draft?: string; attachment?: string; material?: string }>;
}) {
  const { assignmentId } = await params;
  const query = await searchParams;
  const assignment = await learnerPageRequest<Assignment>(
    `/api/v1/me/assignments/${encodeURIComponent(assignmentId)}`,
  );
  const canStart = assignment.allowed_commands.includes("start");
  const submitCommand = assignment.allowed_commands.find((command) =>
    ["submit", "submit_revision"].includes(command),
  );
  const latestVersion = assignment.submission?.versions.at(-1);
  const initialBody = assignment.draft?.body
    ?? (submitCommand === "submit_revision" ? latestVersion?.body ?? "" : "");
  const initialAttachmentIds = assignment.draft?.attachment_ids ?? [];
  const experience = "learning_blocks" in assignment.learning_experience
    ? assignment.learning_experience
    : null;
  const requiredMaterials = assignment.learning_materials.filter((material) => material.required);
  const materialsReady = requiredMaterials.every((material) => material.completed_at !== null);

  return (
    <article className="learner-task-page">
      <header className="task-hero-card">
        <div className="task-identity">
          <span aria-hidden="true">
            {assignment.journey_stage?.stage_kind === "ASSESSMENT" ? "◇" : "●"}
          </span>
          <p>
            {assignment.journey_stage?.title ?? assignment.stable_task_key}
            <small>V{assignment.task_version}</small>
          </p>
        </div>
        <h1>{assignment.task_title}</h1>
        <p>{assignment.journey_stage?.short_description ?? assignment.task_purpose}</p>
        <div className="task-time" aria-label={`预计 ${assignment.estimated_duration_minutes} 分钟`}>
          <i aria-hidden="true" /> {assignment.estimated_duration_minutes} min
        </div>
      </header>

      {assignment.learning_materials.length > 0 ? (
        <section className="learning-materials" aria-labelledby="learning-materials-title">
          <div className="learning-materials-heading">
            <div>
              <p className="section-label">先完成输入</p>
              <h2 id="learning-materials-title">学习材料</h2>
            </div>
            <strong>
              {requiredMaterials.filter((material) => material.completed_at).length}
              /{requiredMaterials.length}
            </strong>
          </div>
          {query.material === "completed" ? (
            <p className="success-text" role="status">完成事实已保存，可在重新登录后恢复。</p>
          ) : null}
          <ol className="learning-material-list">
            {assignment.learning_materials.map((material, index) => (
              <li className={material.completed_at ? "is-complete" : ""} key={material.key}>
                <div className="learning-material-order" aria-hidden="true">
                  {material.completed_at ? "✓" : String(index + 1).padStart(2, "0")}
                </div>
                <article>
                  <p>
                    {material.source_label} · {material.estimated_duration_minutes} min
                    {material.required ? " · 必读" : " · 选读"}
                  </p>
                  <h3>{material.title}</h3>
                  {material.kind === "TEXT" ? <div>{material.body}</div> : (
                    <a href={material.url ?? "#"} target="_blank" rel="noreferrer">
                      打开 {new URL(material.url ?? "https://invalid.example").hostname}
                    </a>
                  )}
                  {material.completed_at ? (
                    <span className="material-complete-label">已完成</span>
                  ) : (
                    <form action={completeLearningMaterial}>
                      <input type="hidden" name="assignment_id" value={assignment.id} />
                      <input type="hidden" name="task_version" value={assignment.task_version} />
                      <input type="hidden" name="material_key" value={material.key} />
                      <input type="hidden" name="idempotency_key" value={randomUUID()} />
                      <button className="button primary compact" type="submit">
                        完成本材料
                      </button>
                    </form>
                  )}
                </article>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {experience && assignment.learning_materials.length === 0 ? (
        <section className="learning-experience" aria-labelledby="learning-experience-title">
          <div className="learning-schedule">
            <span>{experience.schedule.start}</span>
            <i aria-hidden="true" />
            <span>{experience.schedule.end}</span>
            <strong>{experience.mode.replaceAll("_", " ")}</strong>
          </div>
          <p className="section-label">先探索，再输出</p>
          <h2 id="learning-experience-title">本阶段输入</h2>
          <div className="learning-block-grid">
            {experience.learning_blocks.map((block, index) => (
              <article className="learning-block" key={`${block.kind}-${block.title}`}>
                <span className="learning-block-index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <p>{block.kind.replaceAll("_", " ")}</p>
                <h3>{block.title}</h3>
                <div>{block.body}</div>
              </article>
            ))}
          </div>
          <div className="learning-checks">
            <h3>停一下，确认你能回答</h3>
            <ul className="checklist">
              {experience.knowledge_checks.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          {experience.schedule.break_after ? (
            <p className="learning-break">完成后 · {experience.schedule.break_after}</p>
          ) : null}
        </section>
      ) : (
        <section className="task-moves" aria-labelledby="task-moves-title">
          <p className="section-label">这一站</p>
          <h2 id="task-moves-title">沿着动作前进</h2>
          <ol>
            {assignment.instructions.map((item) => <li key={item}>{item}</li>)}
          </ol>
        </section>
      )}

      <details className="task-contract">
        <summary>完成边界</summary>
        <p>{assignment.learner_outcome}</p>
        <div className="task-contract-columns">
          <div>
            <h3>完成标准</h3>
            <ul className="checklist">
              {assignment.completion_criteria.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <div>
            <h3>交付内容</h3>
            <ul className="checklist">
              {assignment.required_deliverables.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
        {assignment.reference_materials.length > 0 ? (
          <ul className="checklist">
            {assignment.reference_materials.map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : null}
      </details>

      <section className="task-workspace" aria-labelledby="task-workspace-title">
      <p className="section-label">完成本阶段</p>
      <h2 id="task-workspace-title">
        {assignment.journey_stage?.stage_kind === "ASSESSMENT" ? "提交你的作答" : "留下学习证据"}
      </h2>

      {query.draft === "saved" ? (
        <p className="success-text" role="status">草稿已保存，刷新后仍可恢复。</p>
      ) : null}
      {query.attachment === "ready" ? (
        <p className="success-text" role="status">附件已校验并通过本地隔离扫描，可加入提交。</p>
      ) : null}
      {query.attachment === "deleted" ? (
        <p className="success-text" role="status">未绑定附件已删除。</p>
      ) : null}

      {assignment.latest_revision_feedback ? (
        <section className="feedback-callout" aria-labelledby="revision-feedback-title">
          <h3 id="revision-feedback-title">主管要求修订</h3>
          <p>{assignment.latest_revision_feedback}</p>
          <p className="status-meta">旧版本和旧评审保持只读，本次提交会追加新版本。</p>
        </section>
      ) : null}

      {!materialsReady ? (
        <p className="task-locked-message" role="status">
          完成全部必读材料后，小任务会在这里解锁。
        </p>
      ) : null}

      {canStart && materialsReady ? (
        <form action={startAssignment}>
          <input type="hidden" name="assignment_id" value={assignment.id} />
          <input type="hidden" name="revision" value={assignment.revision} />
          <button className="button primary" type="submit">开始这一站</button>
        </form>
      ) : null}

      {submitCommand && materialsReady ? (
        <>
          {assignment.allowed_attachment_types.length > 0 ? (
            <section className="attachment-workspace" aria-labelledby="attachment-title">
              <h3 id="attachment-title">附件（可选）</h3>
              <p className="status-meta">
                支持 TXT、PDF、PNG、JPEG；单个不超过 {Math.floor(assignment.max_attachment_size_bytes / 1024 / 1024)} MiB。
                文件由浏览器直传私有对象存储，只在服务端复核 hash、内容类型并通过安全扫描后可提交。
              </p>
              <AttachmentUploader assignmentId={assignment.id} />
              {assignment.available_attachments.length > 0 ? (
                <ul className="attachment-list">
                  {assignment.available_attachments.map((attachment) => (
                    <li key={attachment.id}>
                      <span>
                        <strong>{attachment.original_filename}</strong>
                        <small>READY · {Math.ceil(attachment.size_bytes / 1024)} KiB</small>
                      </span>
                      <form action={deleteSubmissionAttachment}>
                        <input type="hidden" name="assignment_id" value={assignment.id} />
                        <input type="hidden" name="attachment_id" value={attachment.id} />
                        <button className="button secondary compact" type="submit">删除未绑定附件</button>
                      </form>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="status-meta">暂无 READY 附件；纯文本提交仍可继续。</p>
              )}
            </section>
          ) : (
            <p className="status-meta">当前固定任务版本不接收附件，可直接提交结构化文本。</p>
          )}
          <SubmissionComposer
            assignmentId={assignment.id}
            assignmentRevision={assignment.revision}
            command={submitCommand}
            initialBody={initialBody}
            initialAttachmentIds={initialAttachmentIds}
            attachments={assignment.available_attachments}
            submissionIdempotencyKey={randomUUID()}
            draftIdempotencyKey={randomUUID()}
            responseSections={experience?.response_sections ?? []}
            requiresReview={
              assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"
            }
          />
        </>
      ) : null}

      {assignment.allowed_commands.length === 0 ? (
        <p className="notice">这一站暂时没有可执行动作。</p>
      ) : null}
      </section>

      {assignment.submission ? (
        <section className="submission-history" aria-labelledby="submission-history-title">
          <h2 id="submission-history-title">提交历史</h2>
          <p className="status-meta">
            当前为 Version {assignment.submission.current_version_no}；历史版本和评审引用永久只读。
          </p>
          {assignment.submission.versions.map((version) => (
            <article className="history-version" key={version.id}>
              <h3>Version {version.version_no}</h3>
              <p className="status-meta">
                {new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(version.created_at))}
                {version.review_status ? ` · 评审 ${version.review_status}` : ""}
              </p>
              <div className="submission">{version.body}</div>
              {version.attachments.length > 0 ? (
                <ul className="checklist">
                  {version.attachments.map((attachment) => (
                    <li key={attachment.id}>{attachment.original_filename}（只读附件）</li>
                  ))}
                </ul>
              ) : null}
              {version.feedback ? (
                <p><strong>该版本反馈：</strong>{version.feedback}</p>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}

      {assignment.rubric.dimensions.length > 0 ? <details className="task-contract">
        <summary>评审会看什么</summary>
        <ul className="checklist">
          {assignment.rubric.dimensions.map((dimension) => (
            <li key={dimension.dimension_key}>
              <strong>{dimension.title}</strong>：{dimension.evidence_expected}
            </li>
          ))}
        </ul>
      </details> : null}
    </article>
  );
}
