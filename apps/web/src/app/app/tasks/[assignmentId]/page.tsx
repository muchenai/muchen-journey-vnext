import { randomUUID } from "node:crypto";
import Link from "next/link";

import {
  completeLearningMaterial,
  deleteSubmissionAttachment,
  startAssignment,
} from "@/app/actions";
import { ExperienceState, FactLabel } from "@/app/human-experience";
import { Assignment, learnerPageRequest } from "@/lib/server/api";
import { AttachmentUploader } from "./attachment-uploader";
import { SubmissionComposer } from "./submission-composer";

export const dynamic = "force-dynamic";

const formatDate = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Shanghai",
});

export default async function TaskPage({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{
    draft?: string;
    attachment?: string;
    material?: string;
    revision?: string;
  }>;
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
  const nextMaterialKey = assignment.learning_materials.find(
    (material) => material.completed_at === null,
  )?.key;
  const isWaiting = ["SUBMITTED", "IN_REVIEW"].includes(assignment.status);
  const isRevision = assignment.status === "NEEDS_REVISION";
  const revisionVersion = assignment.submission?.versions.findLast(
    (version) => version.decision === "REVISION_REQUIRED",
  );
  const revisionReady = Boolean(
    revisionVersion && revisionVersion.rubric_feedback.length > 0,
  );
  const editingRevision = query.revision === "edit" && revisionReady;

  return (
    <article className="learner-task-page">
      <header className="task-hero-card">
        <div className="task-identity">
          <span aria-hidden="true">
            {assignment.journey_stage?.stage_kind === "ASSESSMENT" ? "◇" : "●"}
          </span>
          <p>
            {assignment.journey_stage?.title ?? assignment.stable_task_key}
            {assignment.journey_stage ? <small>第 {assignment.journey_stage.position + 1} 站</small> : null}
          </p>
        </div>
        <h1>{assignment.task_title}</h1>
        <p>{assignment.journey_stage?.short_description ?? assignment.task_purpose}</p>
        <div className="task-time" aria-label={`预计 ${assignment.estimated_duration_minutes} 分钟`}>
          <i aria-hidden="true" /> {assignment.estimated_duration_minutes} min
        </div>
      </header>

      <section className="task-authority-summary" aria-labelledby="task-authority-title">
        <header>
          <FactLabel kind="system" />
          <div>
            <p className="section-label">权威任务说明</p>
            <h2 id="task-authority-title">开始前，先确认目标与责任边界</h2>
          </div>
        </header>
        <dl>
          <div><dt>为什么做</dt><dd>{assignment.task_purpose}</dd></div>
          <div><dt>任务版本</dt><dd>{assignment.stable_task_key} v{assignment.task_version} · Rubric v{assignment.rubric.version}</dd></div>
          <div><dt>当前状态</dt><dd>{assignment.status}</dd></div>
          <div><dt>正式性质</dt><dd>{assignment.journey_stage?.completion_policy === "LEARNER_EVIDENCE" ? "低风险学习证据" : "正式任务 · 必须真人审核"}</dd></div>
          <div><dt>Reviewer</dt><dd>{assignment.reviewer_display_name} · {assignment.reviewer_role}</dd></div>
          <div><dt>预计投入</dt><dd>{assignment.estimated_duration_minutes} 分钟</dd></div>
          <div><dt>分配时间</dt><dd>{formatDate.format(new Date(assignment.assigned_at))}</dd></div>
          <div><dt>截止与反馈</dt><dd>未配置任务截止时间；TaskVersion 记录反馈 SLA 为 {assignment.feedback_sla_business_days} 个工作日</dd></div>
          <div><dt>可见与敏感级别</dt><dd>{assignment.audience} · {assignment.sensitivity}</dd></div>
          <div><dt>积分规则</dt><dd>积分规则：未配置；积分不会改变正式状态或人才结论</dd></div>
        </dl>
        <details>
          <summary>任务非目标与安全边界</summary>
          <ul className="checklist">
            <li>阅读、点击、自证、AI 建议或积分都不能产生正式通过。</li>
            <li>Journey 内不执行外部生产作业，不上传未获批准的敏感或原始客户数据。</li>
            <li>若任务专属非目标、截止时间或安全字段缺失，页面不会自行补写；请向 {assignment.reviewer_display_name} 或运营确认。</li>
          </ul>
        </details>
      </section>

      {assignment.learning_materials.length > 0 ? (
        <section id="first-learning-input" className="learning-materials" aria-labelledby="learning-materials-title">
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
            {assignment.learning_materials.map((material, index) => {
              const isComplete = material.completed_at !== null;
              const isCurrentMaterial = material.key === nextMaterialKey;
              return (
                <li
                  className={isComplete ? "is-complete" : isCurrentMaterial ? "is-current" : "is-locked"}
                  key={material.key}
                >
                  <div className="learning-material-order" aria-hidden="true">
                    {isComplete ? "✓" : String(index + 1).padStart(2, "0")}
                  </div>
                  <article>
                    <p>
                      {material.source_label} · {material.estimated_duration_minutes} min
                      {material.required ? " · 必读" : " · 选读"}
                    </p>
                    <h3>{material.title}</h3>
                    {isCurrentMaterial ? (
                      material.kind === "TEXT" ? <div>{material.body}</div> : (
                        <a href={material.url ?? "#"} target="_blank" rel="noreferrer">
                          打开 {new URL(material.url ?? "https://invalid.example").hostname}
                        </a>
                      )
                    ) : null}
                    {isComplete ? (
                      <span className="material-complete-label">已完成</span>
                    ) : isCurrentMaterial ? (
                      <form action={completeLearningMaterial}>
                        <input type="hidden" name="assignment_id" value={assignment.id} />
                        <input type="hidden" name="task_version" value={assignment.task_version} />
                        <input type="hidden" name="material_key" value={material.key} />
                        <input type="hidden" name="idempotency_key" value={randomUUID()} />
                        <button className="button primary compact" type="submit">
                          完成本材料
                        </button>
                      </form>
                    ) : (
                      <span className="material-locked-label">完成上一份后开放</span>
                    )}
                  </article>
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      {experience && assignment.learning_materials.length === 0 ? (
        <section id="first-learning-input" className="learning-experience" aria-labelledby="learning-experience-title">
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
      ) : materialsReady ? (
        <section className="task-moves" aria-labelledby="task-moves-title">
          <p className="section-label">这一站</p>
          <h2 id="task-moves-title">沿着动作前进</h2>
          <ol>
            {assignment.instructions.map((item) => <li key={item}>{item}</li>)}
          </ol>
        </section>
      ) : null}

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

      {isWaiting && latestVersion ? (
        <section className="review-waiting-state" aria-labelledby="review-waiting-title">
          <FactLabel kind="system" />
          <p className="section-label">{assignment.status}</p>
          <h2 id="review-waiting-title">
            {assignment.status === "IN_REVIEW" ? "Reviewer 正在处理固定版本" : "提交已接收，等待 Reviewer 开始"}
          </h2>
          <dl>
            <div><dt>SubmissionVersion</dt><dd>Version {latestVersion.version_no} · {latestVersion.id}</dd></div>
            <div><dt>提交时间</dt><dd>{formatDate.format(new Date(latestVersion.created_at))}</dd></div>
            <div><dt>Reviewer / 队列</dt><dd>{assignment.reviewer_display_name} · {assignment.status}</dd></div>
            <div><dt>首次反馈 SLA</dt><dd>TaskVersion 配置为 {assignment.feedback_sla_business_days} 个工作日；运营 SLA 以批准运行配置为准</dd></div>
            <div><dt>通知</dt><dd>任务接口未提供外部通知回执；请以本页权威状态为准</dd></div>
            <div><dt>撤回</dt><dd>正式任务尚未批准撤回；页面不提供绕过审核的动作</dd></div>
          </dl>
          <Link className="button primary" href="#submission-history">查看已提交版本</Link>
        </section>
      ) : null}

      {isRevision && !revisionReady ? (
        <ExperienceState
          kind="error"
          title="返工依据不完整，暂不能正式修订"
          summary="系统没有取得固定旧版本及逐项 Rubric 反馈；为避免覆盖证据或猜测修改范围，当前保持失败关闭。"
          knownFacts={[
            "原提交与已有结论仍保持只读",
            "页面不会自行补写 Reviewer 理由、Rubric 反馈或返工截止时间",
            "需要运营纠正评审引用后，修订入口才会恢复",
          ]}
          action={{ href: "/app", label: "返回当前任务" }}
        />
      ) : null}

      {isRevision && revisionVersion && revisionReady ? (
        <section className="feedback-callout revision-state" aria-labelledby="revision-feedback-title">
          <FactLabel kind="human" />
          <p className="section-label">NEEDS_REVISION</p>
          <h2 id="revision-feedback-title">{assignment.reviewer_display_name} 要求修订</h2>
          <p>{revisionVersion.feedback}</p>
          <ul className="revision-rubric-feedback">
            {revisionVersion.rubric_feedback.map((item) => (
              <li key={item.dimension_key}>
                <strong>{item.dimension_key} · {item.rating}</strong>
                <span>{item.feedback}</span>
              </li>
            ))}
          </ul>
          <p className="status-meta">
            引用旧提交 Version {revisionVersion.version_no}；旧提交与旧结论保持只读。未配置返工截止时间，页面不会自行生成日期。
          </p>
          <p className="status-meta">
            只修改 Reviewer 指出的缺项；其余已提交证据可保留。若签署或证据引用不完整，请先联系运营纠正。
          </p>
          {!editingRevision ? (
            <Link className="button primary" href={`?revision=edit#task-workspace`}>开始修订</Link>
          ) : null}
        </section>
      ) : null}

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

      {submitCommand && materialsReady && (!isRevision || editingRevision) ? (
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
            initialDraftRevision={assignment.draft?.revision ?? null}
            initialDraftUpdatedAt={assignment.draft?.updated_at ?? null}
            responseSections={experience?.response_sections ?? []}
            requiresReview={
              assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"
            }
            isFirstStation={assignment.journey_stage?.position === 0}
            taskVersion={assignment.task_version}
            rubricVersion={assignment.rubric.version}
            reviewerName={assignment.reviewer_display_name}
            visibility={`${assignment.audience} · ${assignment.sensitivity}`}
          />
        </>
      ) : null}

      {assignment.allowed_commands.length === 0 && !isWaiting ? (
        <p className="notice">这一站暂时没有可执行动作。</p>
      ) : null}
      </section>

      {assignment.submission ? (
        <section id="submission-history" className="submission-history" aria-labelledby="submission-history-title">
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
