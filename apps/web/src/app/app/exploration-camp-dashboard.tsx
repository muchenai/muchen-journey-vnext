import { randomUUID } from "node:crypto";
import Link from "next/link";

import { completeRequiredLearningMaterials, startAssignment } from "@/app/actions";
import type { Assignment, JourneyProgress } from "@/lib/server/api";
import { MaterialLaunchButton } from "./material-launch-button";
import { SubmissionComposer } from "./tasks/[assignmentId]/submission-composer";

const URL_PATTERN = /https:\/\/[^\s)\]，。；！？、]+/gu;

function firstMaterialUrl(assignment: Assignment) {
  const material = assignment.learning_materials.find((item) => /公司基础介绍/u.test(item.title))
    ?? assignment.learning_materials[0];
  if (!material) return null;
  if (material.kind === "HTTPS_LINK") return material.url;
  return material.body?.match(URL_PATTERN)?.[0] ?? null;
}

function StageRoute() {
  return (
    <div className="camp-stage-route" aria-label="探索营成长路线">
      <div className="camp-route-node is-current"><span>⌖</span><strong>新人启程</strong></div>
      <i />
      <div className="camp-route-node"><span>◆</span><strong>知识探索</strong></div>
      <i />
      <div className="camp-route-node"><span>◆</span><strong>实践历练</strong></div>
      <i />
      <div className="camp-route-node"><span>◆</span><strong>能力进阶</strong></div>
      <i />
      <div className="camp-route-node"><span>◆</span><strong>独立交付</strong></div>
      <i />
      <div className="camp-route-node is-destination"><span>▥</span><strong>无限可能</strong></div>
    </div>
  );
}

function TaskTimeline({ evidence }: { evidence: boolean }) {
  const steps = ["学习材料", "实践任务", "提交", "审核", "返工", "通过"];
  return (
    <section className="camp-timeline" aria-labelledby="camp-timeline-title">
      <header><h2 id="camp-timeline-title">当前任务列表</h2><span>01 / 09 已探索</span><button aria-label="上一项">‹</button><button aria-label="下一项">›</button></header>
      <ol>
        {steps.map((step, index) => (
          <li className={index < 2 ? "is-complete" : evidence && index === 2 ? "is-current" : ""} key={step}>
            <span>{index < 2 ? "✓" : index + 1}</span><strong>{step}</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ExplorationCampDashboard({
  assignment,
  journey,
  view = "material",
}: {
  assignment: Assignment;
  journey?: JourneyProgress | null;
  view?: "material" | "evidence";
}) {
  const requiredMaterials = assignment.learning_materials.filter((material) => material.required);
  const materialsReady = requiredMaterials.every((material) => material.completed_at !== null);
  const firstMaterial = assignment.learning_materials.find((material) => /公司基础介绍/u.test(material.title))
    ?? assignment.learning_materials[0]
    ?? null;
  const materialUrl = firstMaterialUrl(assignment);
  const submitCommand = assignment.allowed_commands.find((command) =>
    ["submit", "submit_revision", "submit_evidence_revision"].includes(command),
  );
  const canStart = assignment.allowed_commands.includes("start");
  const evidenceView = view === "evidence" && materialsReady;
  const experience = "response_sections" in assignment.learning_experience
    ? assignment.learning_experience
    : null;
  const completedStages = journey?.completed_stages ?? assignment.journey_stage?.position ?? 0;
  const totalStages = journey?.total_stages ?? 9;

  return (
    <div className="exploration-dashboard" data-view={evidenceView ? "evidence" : materialsReady ? "ready" : "material"}>
      <aside className="camp-sidebar">
        <Link className="camp-brand" href="/app"><strong>Muchen Journey</strong><b>沐 晨 旅 程</b><span>从这里，走向更大的自己</span></Link>
        <nav aria-label="学习模块">
          <Link className="is-active" href="/app"><span>◈</span>探索营</Link>
          <span><b>⌂</b>沐晨新手村</span>
          <span><b>♧</b>AI 学院</span>
          <span><b>♙</b>交付约会</span>
        </nav>
        <blockquote>“好的旅程<br />从一个勇敢的开始开始”<small>A BRIGHTER<br />TOMORROW TOGETHER</small></blockquote>
      </aside>

      <main className="camp-main">
        <header className="camp-topbar">
          <div className="camp-motto">探索 · 学习 · 实践 · 成长<small>A BRIGHTER TOMORROW TOGETHER</small></div>
          <div className="camp-search">⌕　搜索任务、知识或关键词…</div>
          <div className="camp-profile"><span>♟</span><strong>你好，新同学<small>继续前进吧！</small></strong></div>
        </header>
        <StageRoute />

        <div className="camp-content-grid">
          <div className="camp-work-column">
            {evidenceView ? (
              <section className="camp-evidence-card">
                {submitCommand ? (
                  <div className="camp-submission-shell">
                    <SubmissionComposer
                      assignmentId={assignment.id}
                      assignmentRevision={assignment.revision}
                      command={submitCommand}
                      initialBody={assignment.draft?.body ?? ""}
                      initialAttachmentIds={assignment.draft?.attachment_ids ?? []}
                      attachments={assignment.available_attachments}
                      submissionIdempotencyKey={randomUUID()}
                      initialDraftRevision={assignment.draft?.revision ?? null}
                      initialDraftUpdatedAt={assignment.draft?.updated_at ?? null}
                      responseSections={["我最想弄清的一件事", "我会从哪里找答案", "下一站我先做什么"]}
                      requiresReview={assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"}
                      isFirstStation
                      taskVersion={assignment.task_version}
                      rubricVersion={assignment.rubric.version}
                      reviewerName={assignment.reviewer_display_name}
                      visibility={`${assignment.audience} · ${assignment.sensitivity}`}
                      expectsExternalDocument={false}
                      taskActionUrl={null}
                      nextVersionNo={(assignment.submission?.current_version_no ?? 0) + 1}
                      primaryActionLabel="确认提交任务证据"
                    />
                  </div>
                ) : (
                  <p className="camp-state-message">当前任务暂时不能提交，请返回任务首页查看状态。</p>
                )}
              </section>
            ) : (
              <section className="camp-current-task" aria-labelledby="camp-current-task-title">
                <header><h1 id="camp-current-task-title">当前任务</h1><span>探索营 · 01/09</span></header>
                <div className="camp-task-body">
                  <img src="/images/exploration-task-material.png" alt="学习材料预览" />
                  <div className="camp-task-copy">
                    <span className="camp-task-icon">▤</span>
                    <div><h2>{firstMaterial?.title ?? assignment.task_title}</h2><p>{assignment.task_purpose}</p></div>
                    <dl>
                      <div><dt>预计时间</dt><dd>{firstMaterial?.estimated_duration_minutes ?? assignment.estimated_duration_minutes} 分钟</dd></div>
                      <div><dt>任务进度</dt><dd>{completedStages} / {totalStages}</dd></div>
                      <div><dt>学习方式</dt><dd>材料 + 任务证据</dd></div>
                    </dl>
                  </div>
                </div>
                <div className="camp-task-actions">
                  {!materialsReady && firstMaterial ? (
                    <form action={completeRequiredLearningMaterials}>
                      <input type="hidden" name="assignment_id" value={assignment.id} />
                      <input type="hidden" name="task_version" value={assignment.task_version} />
                      {requiredMaterials.map((material) => (
                        <span key={material.key}>
                          <input type="hidden" name="material_key" value={material.key} />
                          <input type="hidden" name="idempotency_key" value={randomUUID()} />
                        </span>
                      ))}
                      <MaterialLaunchButton href={materialUrl}>打开第一份必读材料</MaterialLaunchButton>
                    </form>
                  ) : (
                    <>
                      {materialUrl ? <a className="camp-action-button camp-action-secondary" href={materialUrl} target="_blank" rel="noreferrer"><span>▶</span>重新打开材料</a> : null}
                      {canStart ? (
                        <form action={startAssignment}>
                          <input type="hidden" name="assignment_id" value={assignment.id} />
                          <input type="hidden" name="revision" value={assignment.revision} />
                          <input type="hidden" name="destination" value="evidence" />
                          <button className="camp-action-button camp-action-primary" type="submit"><span>▶</span>点击提交任务证据</button>
                        </form>
                      ) : (
                        <Link className="camp-action-button camp-action-primary" href={`/app/tasks/${assignment.id}?view=evidence`}><span>▶</span>点击提交任务证据</Link>
                      )}
                    </>
                  )}
                </div>
              </section>
            )}
            <TaskTimeline evidence={evidenceView} />
          </div>
          <aside className="camp-right-rail" aria-label="成长概览">
            <section><h2>成长进度</h2><strong>{Math.round((completedStages / Math.max(totalStages, 1)) * 100)}%</strong><span><i style={{ width: `${Math.max(5, completedStages / Math.max(totalStages, 1) * 100)}%` }} /></span></section>
            <section><h2>本次探索</h2><p>完成材料后，用自己的话留下真实证据。</p></section>
          </aside>
        </div>
      </main>
    </div>
  );
}
