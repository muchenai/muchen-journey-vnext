import { randomUUID } from "node:crypto";
import type { CSSProperties } from "react";

import {
  completeLearningMaterial,
  deleteSubmissionAttachment,
  startAssignment,
} from "@/app/actions";
import { Assignment, learnerPageRequest } from "@/lib/server/api";
import { AttachmentUploader } from "./attachment-uploader";
import { SubmissionComposer } from "./submission-composer";

export const dynamic = "force-dynamic";

const TRAILING_URL_PUNCTUATION = /[),.;!?，。；！？、）】》]+$/u;
const HTTPS_URL = /(https:\/\/[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+)/gu;

function textWithSafeLinks(value: string | null) {
  if (!value) return null;
  return value.split(HTTPS_URL).map((part, index) => {
    if (!part.startsWith("https://")) return part;
    const trailing = part.match(TRAILING_URL_PUNCTUATION)?.[0] ?? "";
    const href = trailing ? part.slice(0, -trailing.length) : part;
    return (
      <span key={`${href}-${index}`}>
        <a href={href} target="_blank" rel="noreferrer" aria-label="打开学习材料">
          {new URL(href).hostname}
        </a>
        {trailing}
      </span>
    );
  });
}

function ContractLine({ value }: { value: string }) {
  return <span className="contract-line">{textWithSafeLinks(value)}</span>;
}

const MATERIAL_FOCUS_BY_STAGE: Record<string, string> = {
  "DAY-0": "看完后，你只需要能说出：今天会经历什么，第一步从哪里开始？",
  "TRE-001-COMPANY-VALUES": "客户真正购买的，是更多人力，还是可验收的确定性交付？找到一句证据。",
  "TRE-002-AI-DATA-BASICS": "找出一个“表达很流畅，但结论未必可靠”的例子。",
  "TRE-003-PROJECT-AWARENESS": "找出新人进入真实项目后需要承担的一项具体责任。",
  "TRE-004-DELIVERY-FIT": "找出一个应该停下来提问，而不是自行猜测的边界。",
  "ASM-001-RULE-BREAKDOWN": "找出做判断时最容易漏掉的一条规则。",
  "ASM-002-MODEL-JUDGEMENT": "找出支持你选择 A 或 B 的关键证据。",
  "ASM-003-DATA-CONSTRUCTION": "找出一份可交付数据必须保持一致的结构与校验点。",
};

function materialFocus(
  stageKey: string | undefined,
  learnerOutcome: string,
  materialTitle?: string,
  materialIndex?: number,
) {
  if (stageKey === "DAY-0") {
    if (/一封信/u.test(materialTitle ?? "")) {
      return "从信里找一句：公司希望你怎样面对一件需要长期投入的事？";
    }
    return materialIndex === 0
      ? "只看路线：今天先认识什么，之后会用哪三次挑战证明自己？"
      : "只找一个答案：这份材料与你今天的哪一站有关？";
  }
  return MATERIAL_FOCUS_BY_STAGE[stageKey ?? ""]
    ?? `读完后，试着用自己的话回答：${learnerOutcome}`;
}

function materialLinks(value: string | null): string[] {
  if (!value) return [];
  const links = Array.from(value.matchAll(HTTPS_URL), ([match]) =>
    match.replace(TRAILING_URL_PUNCTUATION, ""),
  );
  return Array.from(new Set(links));
}

function LearningMaterialBody({ value }: { value: string | null }) {
  const links = materialLinks(value);
  if (links.length === 0) {
    return <div className="material-body">{textWithSafeLinks(value)}</div>;
  }
  return (
    <>
      <div className="material-link-actions">
        {links.map((href) => (
          <a
            className="button secondary compact material-open-link"
            href={href}
            key={href}
            target="_blank"
            rel="noreferrer"
            aria-label="打开学习材料"
          >
            <span>打开学习材料</span>
            <small>{new URL(href).hostname}</small>
            <i aria-hidden="true">↗</i>
          </a>
        ))}
      </div>
      <details className="material-notes">
        <summary>查看材料说明</summary>
        <div className="material-body">{textWithSafeLinks(value)}</div>
      </details>
    </>
  );
}

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
  const completedRequiredMaterials = requiredMaterials.filter(
    (material) => material.completed_at !== null,
  ).length;
  const materialsReady = requiredMaterials.every((material) => material.completed_at !== null);
  const pendingRequiredMaterials = requiredMaterials.filter((material) => material.completed_at === null);
  const activeMaterialIndex = assignment.learning_materials.findIndex(
    (material) => material.completed_at === null,
  );
  const isAssessment = assignment.journey_stage?.stage_kind === "ASSESSMENT";
  const isTreasure = assignment.journey_stage?.stage_kind === "TREASURE";
  const isDayZero = assignment.journey_stage?.stage_kind === "DAY_0";
  const isFirstTreasure = assignment.journey_stage?.stable_key === "TRE-001-COMPANY-VALUES";
  const stageMarker = isDayZero ? "DAY 0 · 启程" : isTreasure ? "宝藏 · 探索" : "能力评测 · 真人评审";
  const practiceNoun = isAssessment ? "评测" : isDayZero ? "出发卡" : "本主题实践";
  const taskContractText = [
    ...assignment.instructions,
    ...assignment.required_deliverables,
    ...assignment.completion_criteria,
  ].join(" ");
  const expectsExternalDocument = isAssessment
    || /飞书|文档副本|文档链接|提交文档/u.test(taskContractText);
  const stageComplete = assignment.submission !== null && assignment.allowed_commands.length === 0;
  const currentFocus = !materialsReady
    ? isDayZero
      ? "选一个今天最想带走的答案，再打开第 1 条线索"
      : isFirstTreasure
        ? "先做一个 10 秒判断，再打开第 1 条核心线索"
        : `打开第 ${Math.max(1, activeMaterialIndex + 1)} 份材料，带着一个问题去看`
    : canStart
      ? `看清挑战，开始${practiceNoun}`
      : submitCommand
        ? isAssessment ? "完成作答并交给 Reviewer" : "留下这一站的学习证据"
        : stageComplete ? "这一站已经完成" : "等待下一步开放";

  return (
    <article className="learner-task-page" data-stage-kind={assignment.journey_stage?.stage_kind ?? "TASK"}>
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
        <p className="task-hero-label">{stageMarker}</p>
        <h1>{assignment.task_title}</h1>
        <p>{assignment.journey_stage?.short_description ?? assignment.task_purpose}</p>
        <div className="task-time" aria-label={`预计 ${assignment.estimated_duration_minutes} 分钟`}>
          <i aria-hidden="true" /> {assignment.estimated_duration_minutes} min
        </div>
      </header>

      <section className="mission-now" aria-labelledby="mission-now-title">
        <div>
          <p className="section-label">现在只做这一步</p>
          <h2 id="mission-now-title">{currentFocus}</h2>
        </div>
        {!materialsReady && !isFirstTreasure ? (
          <a
            className="button primary compact"
            href={isDayZero ? "#day-zero-choice" : "#learning-materials-title"}
          >
            {isDayZero ? "选一个出发问题" : "打开当前线索"} <span aria-hidden="true">↓</span>
          </a>
        ) : null}
        <div className="mission-progress" aria-label={`已完成 ${completedRequiredMaterials} / ${requiredMaterials.length} 份学习材料`}>
          <span style={{ "--mission-progress": `${requiredMaterials.length === 0 ? 100 : completedRequiredMaterials / requiredMaterials.length * 100}%` } as CSSProperties} />
          <small>{materialsReady ? "输入已就绪" : `${completedRequiredMaterials}/${requiredMaterials.length} 份线索`}</small>
        </div>
      </section>

      {isDayZero && !materialsReady ? (
        <section className="day-zero-briefing" aria-labelledby="day-zero-briefing-title">
          <div className="day-zero-briefing-heading">
            <div>
              <p className="section-label">10 秒看懂今天</p>
              <h2 id="day-zero-briefing-title">一天结束时，你会带走什么？</h2>
              <p>不是背完一套资料，而是完成一条“认识 → 判断 → 行动”的路线。</p>
            </div>
          </div>
          <fieldset id="day-zero-choice" className="day-zero-outcome-choice">
            <legend>先选一个你最想弄清的</legend>
            <label htmlFor="day-zero-choice-company">
              <input id="day-zero-choice-company" name="day-zero-outcome" type="radio" />
              <span aria-hidden="true">01</span>
              <strong>这家公司为什么做 AI 数据？</strong>
              <small>四个宝藏会给你线索</small>
            </label>
            <label htmlFor="day-zero-choice-work">
              <input id="day-zero-choice-work" name="day-zero-outcome" type="radio" />
              <span aria-hidden="true">02</span>
              <strong>真实项目里，我要负责什么？</strong>
              <small>从项目、交付与边界里找答案</small>
            </label>
            <label htmlFor="day-zero-choice-proof">
              <input id="day-zero-choice-proof" name="day-zero-outcome" type="radio" />
              <span aria-hidden="true">03</span>
              <strong>我会怎样证明自己的判断力？</strong>
              <small>最后用三次真实挑战验证</small>
            </label>
          </fieldset>
          <div className="day-zero-rhythm" aria-label="每一站的体验节奏">
            <span><b>1</b> 带一个问题</span>
            <i aria-hidden="true">→</i>
            <span><b>2</b> 找一条线索</span>
            <i aria-hidden="true">→</i>
            <span><b>3</b> 做一个动作</span>
          </div>
          <a className="button primary compact" href="#learning-materials-title">
            从第 1 条线索出发 <span aria-hidden="true">↓</span>
          </a>
        </section>
      ) : null}

      {isFirstTreasure && !materialsReady ? (
        <section className="treasure-opening-choice" aria-labelledby="treasure-opening-choice-title">
          <div>
            <p className="section-label">10 秒先猜</p>
            <h2 id="treasure-opening-choice-title">客户真正买的是什么？</h2>
            <p>不用先读完资料。选一个，再去线索里验证。</p>
          </div>
          <fieldset>
            <legend className="sr-only">选择你当前的判断</legend>
            <label htmlFor="treasure-choice-labor">
              <input id="treasure-choice-labor" name="treasure-opening-choice" type="radio" />
              <span aria-hidden="true">A</span>
              <strong>更多低价人力</strong>
            </label>
            <label htmlFor="treasure-choice-delivery">
              <input id="treasure-choice-delivery" name="treasure-opening-choice" type="radio" />
              <span aria-hidden="true">B</span>
              <strong>可验收的确定性交付</strong>
            </label>
          </fieldset>
          <p className="treasure-choice-feedback treasure-choice-feedback-labor" role="status">
            这是行业最容易走回的旧路。打开线索，看看公司为什么选择另一条路。
          </p>
          <p className="treasure-choice-feedback treasure-choice-feedback-delivery" role="status">
            带着这个判断打开线索：你需要找到一句能支持它的证据。
          </p>
          <a className="button primary compact" href="#learning-materials-title">
            去线索里验证 <span aria-hidden="true">↓</span>
          </a>
        </section>
      ) : null}

      {!isDayZero ? <nav className="task-flow" aria-label="这一站的完成路径">
        <ol>
          <li data-state={materialsReady ? "complete" : "current"}>
            <span>{materialsReady ? "✓" : "01"}</span>
            <strong>收集线索</strong>
            <small>{requiredMaterials.length} 份必读</small>
          </li>
          <li data-state={stageComplete ? "complete" : materialsReady ? "current" : "locked"}>
            <span>{stageComplete ? "✓" : "02"}</span>
            <strong>完成挑战</strong>
            <small>{assignment.required_deliverables[0] ?? "留下这一站的学习证据"}</small>
          </li>
          <li data-state={stageComplete ? "complete" : materialsReady ? "current" : "locked"}>
            <span>{stageComplete ? "✓" : "03"}</span>
            <strong>{isAssessment ? "真人评审" : "点亮路标"}</strong>
            <small>{isAssessment ? "提交后等待真人评审" : "提交后路线自动更新"}</small>
          </li>
        </ol>
      </nav> : null}

      {assignment.learning_materials.length > 0 ? (
        <section className="learning-materials" aria-labelledby="learning-materials-title">
          <div className="learning-materials-heading">
            <div>
              <p className="section-label">{isTreasure ? "宝藏线索" : isAssessment ? "评测输入" : "出发准备"}</p>
              <h2 id="learning-materials-title">
                {isDayZero
                  ? "先打开材料，再留下你的问题"
                  : isFirstTreasure
                    ? "先找证据，不用记住全文"
                    : "每份材料，只找一个答案"}
              </h2>
            </div>
            <strong>
              {completedRequiredMaterials}
              /{requiredMaterials.length}
            </strong>
          </div>
          {query.material === "completed" ? (
            <p className="success-text" role="status">
              {materialsReady ? `材料已完成，现在完成${practiceNoun}。` : "已完成，下一份材料就在下方。"}
            </p>
          ) : null}
          <ol className="learning-material-list">
            {assignment.learning_materials.map((material, index) => {
              const isComplete = material.completed_at !== null;
              const isActive = index === activeMaterialIndex;
              const isLocked = !isComplete && !isActive;
              const itemClass = isComplete ? "is-complete" : isActive ? "is-active" : "is-locked";
              const stageFocus = materialFocus(
                assignment.journey_stage?.stable_key,
                assignment.learner_outcome,
                material.title,
                index,
              );
              const heading = (
                <>
                  <span>
                    {material.source_label} · {material.required ? "核心线索" : "可选补给"}
                  </span>
                  <strong>{material.title}</strong>
                  <small>
                    完整材料约 {material.estimated_duration_minutes} min · 本轮只找 1 个答案
                  </small>
                </>
              );

              return (
                <li className={itemClass} key={material.key}>
                  <div className="learning-material-order" aria-hidden="true">
                    {isComplete ? "✓" : String(index + 1).padStart(2, "0")}
                  </div>
                  {isLocked ? (
                    <div className="learning-material-locked">
                      {heading}
                      <small>完成上一项后解锁</small>
                    </div>
                  ) : (
                    <details className="learning-material-card" open={isActive}>
                      <summary>{heading}</summary>
                      <div className="learning-material-content">
                        <div className="material-focus-prompt">
                          <span aria-hidden="true">?</span>
                          <div>
                            <small>不用通读，先带着这一个问题</small>
                            <strong>{stageFocus}</strong>
                          </div>
                        </div>
                        {material.kind === "TEXT" ? (
                          <LearningMaterialBody value={material.body} />
                        ) : (
                          <a
                            className="button secondary compact material-open-link"
                            href={material.url ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="打开学习材料"
                          >
                            <span>打开学习材料</span>
                            <small>{new URL(material.url ?? "https://invalid.example").hostname}</small>
                            <i aria-hidden="true">↗</i>
                          </a>
                        )}
                        {isComplete ? (
                          <span className="material-complete-label">已完成</span>
                        ) : (
                          <form action={completeLearningMaterial}>
                            <input type="hidden" name="assignment_id" value={assignment.id} />
                            <input type="hidden" name="task_version" value={assignment.task_version} />
                            <input type="hidden" name="material_key" value={material.key} />
                            <input type="hidden" name="idempotency_key" value={randomUUID()} />
                            <input
                              type="hidden"
                              name="final_required_material"
                              value={material.required && pendingRequiredMaterials.length === 1 ? "true" : "false"}
                            />
                            <button
                              className={`button ${material.required ? "primary" : "secondary"} compact`}
                              type="submit"
                            >
                              {material.required && pendingRequiredMaterials.length === 1
                                ? `我找到答案了，开始${practiceNoun}`
                                : "我找到答案了，继续"}
                            </button>
                          </form>
                        )}
                      </div>
                    </details>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      {isTreasure && materialsReady ? (
        <section className="treasure-unlocked" aria-labelledby="treasure-unlocked-title">
          <span className="treasure-seal" aria-hidden="true">✦</span>
          <div>
            <p className="section-label">线索已收集</p>
            <h2 id="treasure-unlocked-title">宝藏还差你的判断</h2>
            <p>把刚刚看到的内容变成自己的证据，完成后这枚路标才会真正点亮。</p>
          </div>
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
      ) : null}

      <section className="task-brief" aria-labelledby="task-brief-title">
        <p className="section-label">{materialsReady ? (isAssessment ? "能力挑战" : "轮到你行动") : "材料看完后"}</p>
        <h2 id="task-brief-title">
          {isDayZero ? "完成一张三句出发卡" : assignment.required_deliverables[0] ?? "留下这一站的学习证据"}
        </h2>
        <p className="task-outcome">
          {isDayZero
            ? "不用复述材料。写清你想弄懂什么、从哪里找答案、下一站先做什么。"
            : materialsReady
              ? "把刚才找到的线索，变成你自己的判断。"
              : "先不用作答。带着上面的一个问题完成材料，再回来行动。"}
        </p>

        {isDayZero ? (
          <div className="day-zero-departure-card" aria-labelledby="task-deliverables-title">
            <div>
              <p className="section-label">三段就够</p>
              <h3 id="task-deliverables-title">你的出发卡</h3>
            </div>
            <ol>
              <li><span>01</span><strong>我最想弄清什么？</strong><small>从上面的三个问题里选一个</small></li>
              <li><span>02</span><strong>我会去哪里找答案？</strong><small>写下一份材料或一个真实场景</small></li>
              <li><span>03</span><strong>下一站先做什么？</strong><small>给自己一个可以立即开始的动作</small></li>
            </ol>
          </div>
        ) : isFirstTreasure && materialsReady ? (
          <div className="treasure-response-cues" aria-labelledby="task-deliverables-title">
            <div>
              <p className="section-label">3–5 句话就够</p>
              <h3 id="task-deliverables-title">把答案放进这三格</h3>
            </div>
            <ol>
              <li><span>01</span><strong>公司在解决什么问题？</strong><small>用你自己的话写一句</small></li>
              <li><span>02</span><strong>你选择或质疑哪项命题？</strong><small>带上刚才找到的证据</small></li>
              <li><span>03</span><strong>未来一周你会做什么？</strong><small>写一个别人看得见的动作</small></li>
            </ol>
          </div>
        ) : (
          <div className="task-brief-deliverables" aria-labelledby="task-deliverables-title">
            <h3 id="task-deliverables-title">这一站只交付</h3>
            <ul className="checklist">
              {assignment.required_deliverables.map((item) => (
                <li key={item}><ContractLine value={item} /></li>
              ))}
            </ul>
          </div>
        )}

        {isFirstTreasure || isDayZero ? (
          <details className="treasure-method-details">
            <summary>{isDayZero ? "需要帮助？查看完整要求" : "需要提示？查看完成方法"}</summary>
            <ol className="checklist">
              {assignment.instructions.map((item) => (
                <li key={item}><ContractLine value={item} /></li>
              ))}
            </ol>
          </details>
        ) : (
          <div className="task-supporting-rules task-contract-columns">
            <div>
              <h3><span aria-hidden="true">→</span> 怎么完成</h3>
              <ol className="checklist">
                {assignment.instructions.map((item) => (
                  <li key={item}><ContractLine value={item} /></li>
                ))}
              </ol>
            </div>
            {assignment.reference_materials.length > 0 ? (
              <div>
                <h3>参考资料</h3>
                <ul className="checklist">
                  {assignment.reference_materials.map((item) => (
                    <li key={item}>{textWithSafeLinks(item)}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
        <details className="task-success-criteria">
          <summary>怎样算完成？</summary>
          <p>{assignment.learner_outcome}</p>
          <ul className="checklist">
            {assignment.completion_criteria.map((item) => (
              <li key={item}><ContractLine value={item} /></li>
            ))}
          </ul>
        </details>
      </section>

      {materialsReady ? <section id="task-workspace" className="task-workspace" aria-labelledby="task-workspace-title">
      <p className="section-label">{assignment.latest_revision_feedback ? "Reviewer 已回应" : "你的行动"}</p>
      <h2 id="task-workspace-title">
        {assignment.latest_revision_feedback
          ? "带着反馈，再走一步"
          : isDayZero ? "写下你的三句出发卡" : isAssessment ? "完成这次能力挑战" : "留下你的判断与证据"}
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
          <span aria-hidden="true">↳</span>
          <div>
          <h3 id="revision-feedback-title">Reviewer 留给你的下一步</h3>
          <p>{assignment.latest_revision_feedback}</p>
          </div>
        </section>
      ) : null}

      {canStart ? (
        <form action={startAssignment}>
          <input type="hidden" name="assignment_id" value={assignment.id} />
          <input type="hidden" name="revision" value={assignment.revision} />
          <button className="button primary" type="submit">开始{practiceNoun}</button>
        </form>
      ) : null}

      {submitCommand ? (
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
          ) : null}
          <SubmissionComposer
            assignmentId={assignment.id}
            assignmentRevision={assignment.revision}
            command={submitCommand}
            initialBody={initialBody}
            initialAttachmentIds={initialAttachmentIds}
            attachments={assignment.available_attachments}
            submissionIdempotencyKey={randomUUID()}
            draftIdempotencyKey={randomUUID()}
            responseSections={isDayZero
              ? ["我最想弄清的一件事", "我会从哪里找答案", "下一站我先做什么"]
              : experience?.response_sections ?? []}
            requiresReview={
              assignment.journey_stage?.completion_policy !== "LEARNER_EVIDENCE"
            }
            expectsExternalDocument={expectsExternalDocument}
          />
        </>
      ) : null}

      {assignment.allowed_commands.length === 0 ? (
        <p className="notice">这一站暂时没有可执行动作。</p>
      ) : null}
      </section> : null}

      {assignment.submission ? (
        <details className="submission-history">
          <summary>查看提交历史</summary>
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
        </details>
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
