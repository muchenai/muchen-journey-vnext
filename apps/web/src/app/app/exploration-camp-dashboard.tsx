import { randomUUID } from "node:crypto";
import Link from "next/link";

import { completeRequiredLearningMaterials, startAssignment } from "@/app/actions";
import type { Assignment, JourneyProgress, JourneyProgressNode } from "@/lib/server/api";
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

function nodeStatusLabel(node: JourneyProgressNode) {
  if (node.status === "COMPLETED") return "已完成";
  if (node.status === "CURRENT") return "进行中";
  return "未解锁";
}

function ConsoleHeader({ completed, total }: { completed: number; total: number }) {
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <header className="journey-console-header">
      <Link href="/app"><span>MUCHEN JOURNEY</span><b>探索营 · 成长任务中心</b></Link>
      <div className="journey-console-progress" aria-label={`已完成 ${completed} 项，共 ${total} 项`}>
        <i><em style={{ width: `${progress}%` }} /></i>
        <small>{completed} / {total} 已完成</small>
        <Link href="/app">任务档案</Link>
      </div>
    </header>
  );
}

function JourneyBoard({ assignment, journey, learnerDisplayName }: {
  assignment: Assignment;
  journey: JourneyProgress;
  learnerDisplayName: string;
}) {
  const total = journey.total_stages || journey.nodes.length;
  const completed = journey.completed_stages;
  const current = journey.nodes.find((node) => node.status === "CURRENT") ?? journey.nodes[0];
  const currentNumber = current ? current.position + 1 : Math.min(completed + 1, total);
  const done = completed >= total && total > 0;

  return (
    <div className="journey-console-shell journey-board-page">
      <div className="journey-console-vignette" aria-hidden="true" />
      <ConsoleHeader completed={completed} total={total} />
      <section className="journey-campaign-hero">
        <div>
          <span className="journey-task-eyebrow">你好，{learnerDisplayName || "新同学"} · 你的成长航线</span>
          <h1>{done ? "全部任务已完成" : `下一站：第 ${currentNumber} 个任务`}</h1>
          <p>{done
            ? "这段探索营旅程已经完成，你可以回看每一站留下的成长证据。"
            : "完成材料并提交真实任务证据后，下一站会由系统自动解锁；草稿与正式提交都会保存在服务器。"}</p>
          {current ? <Link className="journey-console-primary" href={`/app/tasks/${current.assignment_id}`}>{done ? "查看当前旅程" : "继续当前任务"}<span aria-hidden="true">→</span></Link> : null}
        </div>
        <div className="journey-hero-orbit"><b>{completed}<small>/{String(total).padStart(2, "0")}</small></b><span>完成进度</span></div>
      </section>

      <section className="journey-task-board" aria-labelledby="journey-task-board-title">
        <header><div><span>探索营</span><h2 id="journey-task-board-title">全部成长任务</h2></div><small>旅程版本 V{journey.version}</small></header>
        <div className="journey-task-grid">
          {journey.nodes.map((node) => {
            const currentAssignment = node.assignment_id === assignment.id;
            const card = (
              <article className={`journey-task-tile is-${node.status.toLowerCase()}${currentAssignment ? " is-active" : ""}`}>
                <span className="journey-tile-number">{String(node.position + 1).padStart(2, "0")}</span>
                <img src="/images/journey-v2-task-icon.png" alt="" />
                <span className="journey-status-pill">{nodeStatusLabel(node)}</span>
                <h3>{node.title}</h3>
                <p>{node.short_description}</p>
                <footer><small>{node.completion_policy === "REVIEW_REQUIRED" ? "需要真人评审" : "提交证据后完成"}</small><strong>{node.status === "LOCKED" ? "需要完成上一任务" : node.status === "COMPLETED" ? "回看任务 →" : "进入任务 →"}</strong></footer>
              </article>
            );
            return node.status === "LOCKED"
              ? <div aria-disabled="true" key={node.assignment_id}>{card}</div>
              : <Link href={`/app/tasks/${node.assignment_id}`} key={node.assignment_id}>{card}</Link>;
          })}
        </div>
      </section>
    </div>
  );
}

function MaterialView({ assignment, totalStages }: { assignment: Assignment; totalStages: number }) {
  const requiredMaterials = assignment.learning_materials.filter((material) => material.required);
  const materialsReady = requiredMaterials.every((material) => material.completed_at !== null);
  const firstMaterial = assignment.learning_materials.find((material) => /公司基础介绍/u.test(material.title)) ?? assignment.learning_materials[0] ?? null;
  const materialUrl = firstMaterialUrl(assignment);
  const canStart = assignment.allowed_commands.includes("start");
  const position = (assignment.journey_stage?.position ?? 0) + 1;

  return (
    <div className="journey-console-shell journey-detail-page">
      <div className="journey-console-vignette" aria-hidden="true" />
      <ConsoleHeader completed={Math.max(0, position - 1)} total={totalStages} />
      <Link className="journey-back-link" href="/app">← 返回任务总览</Link>
      <section className="journey-material-panel">
        <div className="journey-material-copy">
          <span className="journey-task-eyebrow">探索营 · {String(position).padStart(2, "0")} / {String(totalStages).padStart(2, "0")}</span>
          <div className="journey-material-title"><img src="/images/journey-v2-task-icon.png" alt="" /><div><small>当前任务</small><h1>{firstMaterial?.title ?? assignment.task_title}</h1></div></div>
          <p>{assignment.task_purpose}</p>
          <dl><div><dt>预计时间</dt><dd>{firstMaterial?.estimated_duration_minutes ?? assignment.estimated_duration_minutes} 分钟</dd></div><div><dt>学习方式</dt><dd>材料 + 任务证据</dd></div></dl>
          <div className="journey-material-actions">
            {!materialsReady && firstMaterial ? (
              <form action={completeRequiredLearningMaterials}>
                <input type="hidden" name="assignment_id" value={assignment.id} />
                <input type="hidden" name="task_version" value={assignment.task_version} />
                {requiredMaterials.map((material) => <span key={material.key}><input type="hidden" name="material_key" value={material.key} /><input type="hidden" name="idempotency_key" value={randomUUID()} /></span>)}
                <MaterialLaunchButton href={materialUrl}>打开第一份材料</MaterialLaunchButton>
              </form>
            ) : (
              <>
                {materialUrl ? <a className="journey-console-secondary" href={materialUrl} target="_blank" rel="noreferrer"><img src="/images/journey-v2-reopen-icon.svg" alt="" />重新打开材料</a> : null}
                {canStart ? <form action={startAssignment}><input type="hidden" name="assignment_id" value={assignment.id} /><input type="hidden" name="revision" value={assignment.revision} /><input type="hidden" name="destination" value="evidence" /><button className="journey-console-primary" type="submit"><img src="/images/journey-v2-submit-icon.svg" alt="" />点击提交任务证据</button></form> : <Link className="journey-console-primary" href={`/app/tasks/${assignment.id}?view=evidence`}><img src="/images/journey-v2-submit-icon.svg" alt="" />点击提交任务证据</Link>}
              </>
            )}
          </div>
        </div>
        <img className="journey-material-cover" src="/images/journey-v2-material-cover.png" alt="学习材料预览" />
      </section>
    </div>
  );
}

function EvidenceView({ assignment, totalStages }: { assignment: Assignment; totalStages: number }) {
  const submitCommand = assignment.allowed_commands.find((command) => ["submit", "submit_revision", "submit_evidence_revision"].includes(command));
  const position = (assignment.journey_stage?.position ?? 0) + 1;
  return (
    <div className="journey-console-shell journey-detail-page">
      <div className="journey-console-vignette" aria-hidden="true" />
      <ConsoleHeader completed={Math.max(0, position - 1)} total={totalStages} />
      <Link className="journey-back-link" href={`/app/tasks/${assignment.id}`}>← 返回学习材料</Link>
      <section className="journey-submit-panel">
        <div className="journey-submit-intro"><span className="journey-task-eyebrow">探索营 · {String(position).padStart(2, "0")} / {String(totalStages).padStart(2, "0")}</span><div className="journey-material-title"><img src="/images/journey-v2-task-icon.png" alt="" /><div><small>提交任务证据</small><h1>{assignment.task_title}</h1></div></div><p>{assignment.learner_outcome.replace(/[。！？!?]+$/u, "")}。提交后，系统会按照当前任务规则更新旅程状态。</p></div>
        <div className="journey-submission-shell">
          {submitCommand ? <SubmissionComposer assignmentId={assignment.id} assignmentRevision={assignment.revision} command={submitCommand} initialBody={assignment.draft?.body ?? ""} initialAttachmentIds={assignment.draft?.attachment_ids ?? []} attachments={assignment.available_attachments} submissionIdempotencyKey={randomUUID()} initialDraftRevision={assignment.draft?.revision ?? null} initialDraftUpdatedAt={assignment.draft?.updated_at ?? null} responseSections={["我最想弄清的一件事", "我会从哪里找答案", "下一站我先做什么"]} requiresReview={assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"} isFirstStation={position === 1} taskVersion={assignment.task_version} rubricVersion={assignment.rubric.version} reviewerName={assignment.reviewer_display_name} visibility={`${assignment.audience} · ${assignment.sensitivity}`} expectsExternalDocument={false} taskActionUrl={null} nextVersionNo={(assignment.submission?.current_version_no ?? 0) + 1} primaryActionLabel="确认提交任务证据" /> : <p className="journey-state-message">当前任务暂时不能提交，请返回任务总览查看状态。</p>}
        </div>
      </section>
    </div>
  );
}

export function ExplorationCampDashboard({ assignment, learnerDisplayName, journey, view = "material", mode = "task" }: { assignment: Assignment; learnerDisplayName: string; journey?: JourneyProgress | null; view?: "material" | "evidence"; mode?: "board" | "task" }) {
  if (journey && mode === "board") return <JourneyBoard assignment={assignment} journey={journey} learnerDisplayName={learnerDisplayName} />;
  const totalStages = journey?.total_stages ?? 9;
  return view === "evidence" ? <EvidenceView assignment={assignment} totalStages={totalStages} /> : <MaterialView assignment={assignment} totalStages={totalStages} />;
}
