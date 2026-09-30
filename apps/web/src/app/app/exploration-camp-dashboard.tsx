import { randomUUID } from "node:crypto";
import Link from "next/link";

import { completeRequiredLearningMaterials, startAssignment } from "@/app/actions";
import { formatProductDateTime } from "@/lib/date-time";
import type { Assignment, JourneyProgress, JourneyProgressNode } from "@/lib/server/api";
import { MaterialLaunchButton } from "./material-launch-button";
import { SubmissionComposer } from "./tasks/[assignmentId]/submission-composer";
import { stageUserFacingTitle } from "./stage-title";

const URL_PATTERN = /https:\/\/[^\s)\]，。；！？、]+/gu;

function learningMaterialUrl(material: Assignment["learning_materials"][number]) {
  if (material.kind === "HTTPS_LINK") return material.url;
  return material.body?.match(URL_PATTERN)?.[0] ?? null;
}

function taskInstructionUrl(assignment: Assignment) {
  const urls = assignment.instructions.flatMap((instruction) => instruction.match(URL_PATTERN) ?? []);
  return urls.find((url) => new URL(url).hostname.endsWith(".feishu.cn")) ?? urls[0] ?? null;
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
          {current ? <Link className="journey-console-primary" href={`/app/tasks/${current.assignment_id}${done ? "?view=review" : ""}`}>{done ? "查看当前旅程" : "继续当前任务"}<span aria-hidden="true">→</span></Link> : null}
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
                <h3>{stageUserFacingTitle(node.title)}</h3>
                <p>{node.short_description}</p>
                <footer><small>{node.completion_policy === "REVIEW_REQUIRED" ? "需要真人评审" : "提交证据后完成"}</small><strong>{node.status === "LOCKED" ? "需要完成上一任务" : node.status === "COMPLETED" ? "回看任务 →" : "进入任务 →"}</strong></footer>
              </article>
            );
            return node.status === "LOCKED"
              ? <div aria-disabled="true" key={node.assignment_id}>{card}</div>
              : <Link href={`/app/tasks/${node.assignment_id}${node.status === "COMPLETED" ? "?view=review" : ""}`} key={node.assignment_id}>{card}</Link>;
          })}
        </div>
      </section>
    </div>
  );
}

function MaterialView({ assignment, totalStages }: { assignment: Assignment; totalStages: number }) {
  const requiredMaterials = assignment.learning_materials.filter((material) => material.required);
  const materialsReady = requiredMaterials.every((material) => material.completed_at !== null);
  const visibleMaterials = requiredMaterials.length > 0 ? requiredMaterials : assignment.learning_materials;
  const firstIncompleteIndex = visibleMaterials.findIndex((material) => material.completed_at === null);
  const totalMaterialMinutes = visibleMaterials.reduce((total, material) => total + material.estimated_duration_minutes, 0);
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
          <div className="journey-material-title"><img src="/images/journey-v2-task-icon.png" alt="" /><div><small>当前任务</small><h1>{stageUserFacingTitle(assignment.task_title)}学习输入</h1></div></div>
          <p>{assignment.task_purpose}</p>
          <dl><div><dt>预计时间</dt><dd>{totalMaterialMinutes || assignment.estimated_duration_minutes} 分钟</dd></div><div><dt>学习方式</dt><dd>材料 + 任务证据</dd></div></dl>
          <div className="journey-material-grid" aria-label="学习材料">
            {visibleMaterials.map((material, index) => {
              const completed = material.completed_at !== null;
              const available = completed || index === firstIncompleteIndex;
              const url = learningMaterialUrl(material);
              return (
                <article className={`journey-material-card${completed ? " is-completed" : available ? " is-current" : " is-locked"}`} key={material.key}>
                  <header><span>材料 {String(index + 1).padStart(2, "0")}</span><strong>{completed ? "已完成" : available ? "待学习" : "未开放"}</strong></header>
                  <h2>{material.title}</h2>
                  <p>预计 {material.estimated_duration_minutes} 分钟</p>
                  {completed ? (
                    url ? <a className="journey-material-card-link" href={url} target="_blank" rel="noreferrer"><img src="/images/journey-v2-reopen-icon.svg" alt="" />重新打开材料 {String(index + 1).padStart(2, "0")}</a> : <span className="journey-material-card-note">材料已完成</span>
                  ) : available ? (
                    <form action={completeRequiredLearningMaterials}>
                      <input type="hidden" name="assignment_id" value={assignment.id} />
                      <input type="hidden" name="task_version" value={assignment.task_version} />
                      <input type="hidden" name="material_key" value={material.key} />
                      <input type="hidden" name="idempotency_key" value={randomUUID()} />
                      <MaterialLaunchButton href={url}>打开材料 {String(index + 1).padStart(2, "0")}</MaterialLaunchButton>
                    </form>
                  ) : <span className="journey-material-card-note">完成上一份材料后开放</span>}
                </article>
              );
            })}
          </div>
          {materialsReady ? (
            <div className="journey-material-actions">
              {canStart ? <form action={startAssignment}><input type="hidden" name="assignment_id" value={assignment.id} /><input type="hidden" name="revision" value={assignment.revision} /><input type="hidden" name="destination" value="evidence" /><button className="journey-console-primary" type="submit"><img src="/images/journey-v2-submit-icon.svg" alt="" />点击提交任务证据</button></form> : <Link className="journey-console-primary" href={`/app/tasks/${assignment.id}?view=evidence`}><img src="/images/journey-v2-submit-icon.svg" alt="" />点击提交任务证据</Link>}
            </div>
          ) : null}
        </div>
        <img className="journey-material-cover" src="/images/journey-v2-material-cover.png" alt="学习材料预览" />
      </section>
    </div>
  );
}

function EvidenceView({ assignment, totalStages }: { assignment: Assignment; totalStages: number }) {
  const submitCommand = assignment.allowed_commands.find((command) => ["submit", "submit_revision", "submit_evidence_revision"].includes(command));
  const position = (assignment.journey_stage?.position ?? 0) + 1;
  const isTreasure = assignment.journey_stage?.stage_kind === "TREASURE";
  const experience = "response_sections" in assignment.learning_experience ? assignment.learning_experience : null;
  const responseSections = isTreasure
    ? experience?.response_sections ?? ["我的判断", "支持判断的证据", "下一步行动"]
    : ["我最想弄清的一件事", "我会从哪里找答案", "下一站我先做什么"];
  const taskActionUrl = isTreasure ? taskInstructionUrl(assignment) : null;
  return (
    <div className="journey-console-shell journey-detail-page">
      <div className="journey-console-vignette" aria-hidden="true" />
      <ConsoleHeader completed={Math.max(0, position - 1)} total={totalStages} />
      <Link className="journey-back-link" href={`/app/tasks/${assignment.id}`}>← 返回学习材料</Link>
      <section className="journey-submit-panel">
        <div className="journey-submit-intro"><span className="journey-task-eyebrow">探索营 · {String(position).padStart(2, "0")} / {String(totalStages).padStart(2, "0")}</span><div className="journey-material-title"><img src="/images/journey-v2-task-icon.png" alt="" /><div><small>{isTreasure ? "宝藏测试题" : "提交任务证据"}</small><h1>{stageUserFacingTitle(assignment.task_title)}</h1></div></div><p>{assignment.learner_outcome.replace(/[。！？!?]+$/u, "")}。提交后，系统会按照当前任务规则更新旅程状态。</p></div>
        <div className="journey-submission-shell">
          {submitCommand ? <SubmissionComposer assignmentId={assignment.id} assignmentRevision={assignment.revision} command={submitCommand} initialBody={assignment.draft?.body ?? ""} initialAttachmentIds={assignment.draft?.attachment_ids ?? []} attachments={assignment.available_attachments} submissionIdempotencyKey={randomUUID()} initialDraftRevision={assignment.draft?.revision ?? null} initialDraftUpdatedAt={assignment.draft?.updated_at ?? null} responseSections={responseSections} requiresReview={assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"} isFirstStation={position === 1} taskVersion={assignment.task_version} rubricVersion={assignment.rubric.version} reviewerName={assignment.reviewer_display_name} visibility={`${assignment.audience} · ${assignment.sensitivity}`} expectsExternalDocument={isTreasure} taskActionUrl={taskActionUrl} nextVersionNo={(assignment.submission?.current_version_no ?? 0) + 1} primaryActionLabel="确认提交任务证据" skipFinalConfirmation /> : <p className="journey-state-message">当前任务暂时不能提交，请返回任务总览查看状态。</p>}
        </div>
      </section>
    </div>
  );
}

function ReviewView({ assignment, totalStages }: { assignment: Assignment; totalStages: number }) {
  const position = (assignment.journey_stage?.position ?? 0) + 1;
  const materials = assignment.learning_materials.filter((material) => material.required);
  const visibleMaterials = materials.length > 0 ? materials : assignment.learning_materials;
  const latestVersion = assignment.submission?.versions.at(-1);

  return (
    <div className="journey-console-shell journey-detail-page">
      <div className="journey-console-vignette" aria-hidden="true" />
      <ConsoleHeader completed={position} total={totalStages} />
      <Link className="journey-back-link" href="/app">← 返回任务总览</Link>
      <section className="journey-review-panel" aria-labelledby="journey-review-title">
        <header className="journey-review-heading">
          <div>
            <span className="journey-task-eyebrow">探索营 · {String(position).padStart(2, "0")} / {String(totalStages).padStart(2, "0")}</span>
            <div className="journey-material-title">
              <img src="/images/journey-v2-task-icon.png" alt="" />
              <div><small>任务回看</small><h1 id="journey-review-title">{stageUserFacingTitle(assignment.task_title)}</h1></div>
            </div>
          </div>
          <strong className="journey-review-status"><span aria-hidden="true">✓</span> 已完成</strong>
        </header>

        <div className="journey-review-section">
          <div className="journey-review-section-title"><span>01</span><div><small>LEARNING MATERIALS</small><h2>学习材料</h2></div></div>
          <div className="journey-material-grid" aria-label="已完成的学习材料">
            {visibleMaterials.map((material, index) => {
              const url = learningMaterialUrl(material);
              return (
                <article className="journey-material-card is-completed" key={material.key}>
                  <header><span>材料 {String(index + 1).padStart(2, "0")}</span><strong>已完成</strong></header>
                  <h2>{material.title}</h2>
                  <p>预计 {material.estimated_duration_minutes} 分钟</p>
                  {url ? <a className="journey-material-card-link" href={url} target="_blank" rel="noreferrer"><img src="/images/journey-v2-reopen-icon.svg" alt="" />重新打开材料 {String(index + 1).padStart(2, "0")}</a> : <span className="journey-material-card-note">材料已完成</span>}
                </article>
              );
            })}
          </div>
        </div>

        <div className="journey-review-section">
          <div className="journey-review-section-title"><span>02</span><div><small>SUBMITTED EVIDENCE</small><h2>已提交任务证据</h2></div></div>
          {latestVersion ? (
            <article className="journey-review-evidence">
              <header><strong>Version {latestVersion.version_no}</strong><time>{formatProductDateTime(latestVersion.created_at)}</time></header>
              <div>{latestVersion.body}</div>
              {latestVersion.attachments.length > 0 ? <ul>{latestVersion.attachments.map((attachment) => <li key={attachment.id}>{attachment.original_filename}</li>)}</ul> : null}
              {latestVersion.feedback ? <p><strong>任务反馈：</strong>{latestVersion.feedback}</p> : null}
            </article>
          ) : <p className="journey-state-message">这项任务尚未生成正式提交版本。</p>}
        </div>

        <footer className="journey-review-footer">
          <span>任务版本 V{assignment.task_version} · 证据记录只读保存</span>
          <Link className="journey-console-primary" href="/app">返回任务总览 <span aria-hidden="true">→</span></Link>
        </footer>
      </section>
    </div>
  );
}

export function ExplorationCampDashboard({ assignment, learnerDisplayName, journey, view = "material", mode = "task" }: { assignment: Assignment; learnerDisplayName: string; journey?: JourneyProgress | null; view?: "material" | "evidence" | "review"; mode?: "board" | "task" }) {
  if (journey && mode === "board") return <JourneyBoard assignment={assignment} journey={journey} learnerDisplayName={learnerDisplayName} />;
  const totalStages = journey?.total_stages ?? 9;
  if (view === "review") return <ReviewView assignment={assignment} totalStages={totalStages} />;
  return view === "evidence" ? <EvidenceView assignment={assignment} totalStages={totalStages} /> : <MaterialView assignment={assignment} totalStages={totalStages} />;
}
