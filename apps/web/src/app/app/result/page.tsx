import Link from "next/link";

import {
  acceptControlledTaskHandoff,
  requestNextTrainingStageReview,
} from "@/app/actions";
import { FactLabel } from "@/app/human-experience";
import {
  CurrentAction,
  HandoffDetail,
  IncentiveLedger,
  learnerPageRequest,
  NextTrainingStageReviewRequestList,
  Result,
  Timeline,
} from "@/lib/server/api";

import { stageDisplayTitle } from "../stage-title";

export const dynamic = "force-dynamic";

const formatDate = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Shanghai",
});

const ratingLabels: Record<string, string> = {
  MEETS: "达到要求",
  NEEDS_WORK: "需要改进",
};

const nextStageLabels = {
  READY: "进入下一训练阶段",
  DEFER: "先巩固并复测",
  NOT_READY: "暂停并由真人重新安排",
} as const;

const reviewStatusLabels = {
  RECEIVED: "复核申请已接收",
  IN_REVIEW: "独立 Reviewer 复核中",
  UPHELD: "独立复核维持原决定",
  OVERTURNED: "独立复核已追加替换决定",
  RETURNED_FOR_REVIEW: "已退回重新评审",
} as const;

function timelineDetail(eventType: string, details: Timeline["items"][number]["details"]) {
  if (eventType === "SUBMISSION_VERSION_CREATED") {
    return `提交版本 ${details.version_no ?? "—"}`;
  }
  if (eventType === "EVALUATION_FINALIZED") {
    return details.decision === "PASS" ? "结论：通过" : "评价已定稿";
  }
  if (eventType.startsWith("NOTIFICATION_")) {
    if (details.external_delivery_confirmed === true) {
      return "飞书服务已接受通知请求。";
    }
    if (details.channel === "LOCAL_TEST") {
      return "本地测试记录不代表外部送达。";
    }
    return "通知尚未取得外部回执；核心结果不受影响。";
  }
  return null;
}

export default async function ResultPage({
  searchParams,
}: {
  searchParams: Promise<{
    enrollment_id?: string;
    review_requested?: string;
    handoff_accepted?: string;
  }>;
}) {
  const query = await searchParams;
  const enrollmentQuery = query.enrollment_id
    ? `&enrollment_id=${encodeURIComponent(query.enrollment_id)}`
    : "";
  const resultQuery = query.enrollment_id
    ? `?enrollment_id=${encodeURIComponent(query.enrollment_id)}`
    : "";
  const [result, timeline, reviewRequests, incentives, currentAction] = await Promise.all([
    learnerPageRequest<Result>(`/api/v1/me/result${resultQuery}`),
    learnerPageRequest<Timeline>(`/api/v1/me/timeline?limit=100${enrollmentQuery}`),
    learnerPageRequest<NextTrainingStageReviewRequestList>(
      "/api/v1/me/next-training-stage-review-requests",
    ),
    learnerPageRequest<IncentiveLedger>("/api/v1/me/incentives"),
    learnerPageRequest<CurrentAction>(`/api/v1/me/current-action${resultQuery}`),
  ]);
  const handoff = await learnerPageRequest<HandoffDetail>(
    `/api/v1/me/handoffs/${result.handoff.id}`,
  );
  const notificationEvidence = result.notification.external_delivery_confirmed
    ? "飞书服务已确认接受通知请求。"
    : result.notification.delivery_scope === "FEISHU"
      ? "尚无飞书服务回执；结果仍以本页为准。"
      : "本地测试记录不代表外部送达。";
  const latestReviewRequest = reviewRequests.items[0] ?? null;
  const journeyNodes = currentAction.journey?.nodes ?? [];
  const dayZero = journeyNodes.find((node) => node.stage_kind === "DAY_0");
  const treasureNodes = journeyNodes.filter((node) => node.stage_kind === "TREASURE");
  const assessmentNodes = new Map(
    journeyNodes
      .filter((node) => node.stage_kind === "ASSESSMENT")
      .map((node) => [node.stable_key, node]),
  );
  return (
    <article className="result-page">
      <header className="panel result-hero">
        <div className="result-sky" aria-hidden="true">
          <span className="result-horizon" />
          <div className="completion-orbit">
            {Array.from({ length: 8 }, (_, index) => <i key={index} />)}
          </div>
        </div>
        <div className="result-hero-copy">
          <p className="journey-whisper">The journey continues.</p>
          {dayZero ? (
            <Link
              className="result-kicker result-kicker-link"
              href={`/app/tasks/${dayZero.assignment_id}`}
              aria-label="回看启程"
            >
              <span aria-hidden="true">✓</span> 8 / 8 路标已点亮
            </Link>
          ) : (
            <p className="result-kicker"><span aria-hidden="true">✓</span> 8 / 8 路标已点亮</p>
          )}
          <h1>你走完了这段探索。</h1>
          <p className="result-hero-statement">也留下了只属于你的判断。</p>
          <p className="lede">{result.summary}</p>
          <p className="status-meta">
            结果生成于 <time dateTime={result.created_at}>{formatDate.format(new Date(result.created_at))}</time>
          </p>
        </div>
      </header>

      <section className="panel result-section result-collection" aria-labelledby="collection-title">
        <div className="result-section-heading">
          <div>
            <p className="section-label">探索通行证已盖章</p>
            <h2 id="collection-title">你带走的，不只是答案</h2>
          </div>
          <span className="result-pass-stamp" aria-label="四枚宝藏与三项能力证据已确认">Journey 8 / 8</span>
        </div>
        <div className="treasure-collection" aria-label="已完成四个宝藏主题">
          {treasureNodes.map((node, index) => {
            const title = stageDisplayTitle(node.title);
            return (
              <Link
                className="result-revisit-link"
                href={`/app/tasks/${node.assignment_id}`}
                aria-label={`回看宝藏 ${index + 1}：${title}`}
                key={node.assignment_id}
              >
                <article>
                  <span aria-hidden="true">✦</span>
                  <small>宝藏 {index + 1}</small>
                  <strong>{title}</strong>
                </article>
              </Link>
            );
          })}
        </div>
        <div className="ability-collection" aria-label="已通过三项能力评测">
          {result.journey_evaluations.map((evaluation, index) => {
            const node = assessmentNodes.get(evaluation.stage_key);
            const title = stageDisplayTitle(evaluation.stage_title);
            const card = (
              <article>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>Reviewer 已确认</small>
                  <strong>{title}</strong>
                </div>
              </article>
            );
            return node ? (
              <Link
                className="result-revisit-link"
                href={`/app/tasks/${node.assignment_id}`}
                aria-label={`回看能力评测 ${index + 1}：${title}`}
                key={evaluation.id}
              >
                {card}
              </Link>
            ) : (
              <div key={evaluation.id}>{card}</div>
            );
          })}
        </div>
      </section>

      <section className="panel result-section result-next-step-summary" aria-labelledby="next-step-summary-title">
        <p className="section-label">下一步</p>
        <h2 id="next-step-summary-title">{result.handoff.next_step_title}</h2>
        <p>{result.handoff.instructions}</p>
      </section>

      <details className="panel result-section result-details">
        <summary>查看评审与准入详情</summary>
        <p>正式结果、真人 Reviewer 结论和下一训练阶段决定分别记录；下方各区展示权威事实与人工复核入口。</p>
      </details>

      <section className="panel result-section" aria-labelledby="decision-layers-title">
        <p className="section-label">01 · 结论分层</p>
        <h2 id="decision-layers-title">结果、真人结论与下一训练阶段分开记录</h2>
        <div className="decision-layer-grid">
          <article>
            <FactLabel kind="completion" />
            <span className="material-status complete">学习完成</span>
            <strong>{result.learning_completion.completed_stages} / {result.learning_completion.total_stages} 站</strong>
            <p>本次学习与提交证据已保存。</p>
          </article>
          <article>
            <FactLabel kind="human" />
            <span className="material-status complete">Reviewer 结论</span>
            <strong>探索营通过</strong>
            <p>{result.reviewer_conclusion.overall_feedback}</p>
            <small>
              {result.reviewer_conclusion.reviewer_display_name} · 固定 SubmissionVersion {result.reviewer_conclusion.submission_version_id}
            </small>
            <small>
              Reviewer AI 披露：{result.reviewer_conclusion.ai_use.used
                ? "已使用建议性 AI，结论仍由真人签署"
                : "未使用 AI"}
            </small>
          </article>
          <article>
            <FactLabel kind="system" />
            <span className="material-status">下一训练阶段决定</span>
            <strong>
              {result.next_training_stage.decision
                ? nextStageLabels[result.next_training_stage.decision]
                : "待授权真人决定"}
            </strong>
            <p>
              {result.next_training_stage.decision_reason
                ?? "本页不根据 AI、积分或自证自动产生下一阶段状态。"}
            </p>
            {result.next_training_stage.signed_at ? (
              <small>
                真人签署于 {formatDate.format(new Date(result.next_training_stage.signed_at))}；
                原决定保持不可变。
              </small>
            ) : null}
          </article>
        </div>
      </section>

      <section className="panel result-section" aria-labelledby="feedback-title">
        <p className="section-label">02 · 三项能力证据</p>
        <h2 id="feedback-title">你留下的判断</h2>
        {result.journey_evaluations.length > 0 ? (
          <div className="ability-results">
            {result.journey_evaluations.map((evaluation, index) => (
              <article key={evaluation.id}>
                <span>0{index + 1}</span>
                <h3>{stageDisplayTitle(evaluation.stage_title)}</h3>
                <p>{evaluation.overall_feedback}</p>
                <details>
                  <summary>展开评审证据</summary>
                  <ul className="result-rubric">
                    {evaluation.rubric_feedback.map((item) => (
                      <li key={item.dimension_key}>
                        <div className="result-rubric-heading">
                          <h3>{item.title}</h3>
                          <span className="material-status complete">
                            {ratingLabels[item.rating] ?? item.rating}
                          </span>
                        </div>
                        <p>{item.feedback ?? "该维度没有补充文字反馈。"}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              </article>
            ))}
          </div>
        ) : (
          <>
            <p className="feedback-summary">{result.evaluation.overall_feedback}</p>
            <ul className="result-rubric">
              {result.evaluation.rubric_feedback.map((item) => (
                <li key={item.dimension_key}>
                  <div className="result-rubric-heading">
                    <h3>{item.title}</h3>
                    <span className="material-status complete">
                      {ratingLabels[item.rating] ?? item.rating}
                    </span>
                  </div>
                  <p>{item.feedback ?? "该历史评价未记录维度级反馈。"}</p>
                </li>
              ))}
            </ul>
          </>
        )}
        <aside className="ai-note" aria-label="AI 摘要状态">
          <FactLabel kind="ai" />
          <strong>人工评价原文</strong>
          <span>页面不使用 AI 改写 Reviewer 结论。</span>
        </aside>
      </section>

      {latestReviewRequest ? (
        <section className="panel result-section" aria-labelledby="review-lineage-title">
          <p className="section-label">03 · 人工复核谱系</p>
          <h2 id="review-lineage-title">
            {reviewStatusLabels[latestReviewRequest.status]}
          </h2>
          <p>{latestReviewRequest.resolution_reason ?? latestReviewRequest.reason}</p>
          <p className="status-meta">
            原 {nextStageLabels[latestReviewRequest.source_decision]} 决定保持不可变；
            {latestReviewRequest.assigned_at
              ? ` 独立 Reviewer 已于 ${formatDate.format(new Date(latestReviewRequest.assigned_at))} 接收。`
              : " 正等待 Operator 分配独立 Reviewer。"}
          </p>
          {latestReviewRequest.replacement_decision_id ? (
            <p className="status-meta">
              替换决定已作为新版本追加，并明确引用本次复核和原决定。
            </p>
          ) : null}
        </section>
      ) : result.next_training_stage.can_request_review
        && result.next_training_stage.decision_id ? (
        <section className="panel result-section" aria-labelledby="review-request-title">
          <p className="section-label">03 · 人工复核入口</p>
          <h2 id="review-request-title">申请独立人工复核</h2>
          <p>
            申请会保留原决定，并由 Operator 分配未参与原决定的 Reviewer；只有独立真人复核可以追加替换决定。
          </p>
          <form action={requestNextTrainingStageReview} className="content-form">
            <input
              type="hidden"
              name="decision_id"
              value={result.next_training_stage.decision_id}
            />
            <label>
              为什么需要复核
              <textarea name="reason" minLength={10} maxLength={2000} required />
            </label>
            <label>
              补充证据引用（可选，不粘贴敏感正文）
              <input name="evidence_ref" minLength={3} maxLength={300} />
            </label>
            <button type="submit">申请人工复核</button>
          </form>
        </section>
      ) : null}

      <p className="status-meta">
        当前仅开放已批准的“下一训练阶段决定”独立人工复核；通用高影响申诉政策尚未获批准，系统不会自行创建申诉状态或承诺时限。
      </p>

      <section className="panel result-section" aria-labelledby="incentive-ledger-title">
        <FactLabel kind="incentive" />
        <p className="section-label">激励独立账本</p>
        <h2 id="incentive-ledger-title">积分只记录激励，不改变正式状态</h2>
        <dl className="incentive-summary">
          <div><dt>积分</dt><dd>{incentives.points_total}</dd></div>
          <div><dt>XP</dt><dd>{incentives.xp_total}</dd></div>
          <div><dt>正式影响</dt><dd>{incentives.formal_effect}</dd></div>
          <div><dt>可解锁人工 Gate</dt><dd>{incentives.can_unlock_human_gate ? "是" : "否"}</dd></div>
        </dl>
        {incentives.entries.length > 0 ? (
          <ol className="incentive-ledger">
            {incentives.entries.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.label ?? entry.incentive_type} {entry.amount === null ? "" : entry.amount}</strong>
                <span>{entry.module_key} · {formatDate.format(new Date(entry.created_at))}</span>
                <code>{entry.rule_ref} · {entry.rule_sha256}</code>
                <small>来源 Outcome {entry.source_outcome_id}{entry.correction_of_entry_id ? ` · 更正 ${entry.correction_of_entry_id}` : ""}</small>
              </li>
            ))}
          </ol>
        ) : (
          <p className="status-meta">尚无激励记录；系统不会用缺失记录推断积分、徽章或排名。</p>
        )}
        <p className="status-meta">
          formal_effect={incentives.formal_effect}；激励不会通过任务、不会产生人才结论，也不会绕过具名真人 Gate。
        </p>
      </section>

      <section className="panel result-section" aria-labelledby="handoff-title">
        <p className="section-label">04 · 唯一下一步</p>
        <h2 id="handoff-title">{result.handoff.next_step_title}</h2>
        <div className="handoff-card">
          <div>
            <span className="handoff-owner-label">交接责任人</span>
            <strong>{result.handoff.owner_display_name}</strong>
          </div>
          <p>{result.handoff.instructions}</p>
        </div>
        <p className="status-meta">
          交接事实生成于 <time dateTime={result.handoff.created_at}>{formatDate.format(new Date(result.handoff.created_at))}</time>；刷新或重放不会新建下一步。
        </p>
        {handoff.acceptance_status === "READY_TO_ACCEPT"
          && handoff.controlled_task_authorization
          && handoff.next_training_stage_decision_id ? (
          <div className="handoff-card">
            <div>
              <span className="handoff-owner-label">受控任务授权</span>
              <strong>已生效，等待本人确认</strong>
            </div>
            <p>
              授权有效至 {formatDate.format(new Date(handoff.controlled_task_authorization.expires_at))}。
              确认只会原子创建一个新手村 Enrollment 和一个 Assignment；不会执行生产作业。
            </p>
            <form action={acceptControlledTaskHandoff} className="content-form">
              <input type="hidden" name="handoff_id" value={result.handoff.id} />
              <input
                type="hidden"
                name="next_training_stage_decision_id"
                value={handoff.next_training_stage_decision_id}
              />
              <input
                type="hidden"
                name="controlled_task_authorization_id"
                value={handoff.controlled_task_authorization.id}
              />
              <input
                type="hidden"
                name="revision"
                value={handoff.controlled_task_authorization.revision}
              />
              <input
                type="hidden"
                name="scope_sha256"
                value={handoff.controlled_task_authorization.scope_sha256}
              />
              <input
                type="hidden"
                name="task_version_sha256"
                value={handoff.controlled_task_authorization.task_version_sha256}
              />
              <input
                type="hidden"
                name="policy_snapshot_sha256"
                value={handoff.controlled_task_authorization.policy_snapshot_sha256}
              />
              <input
                type="hidden"
                name="target_journey_version_id"
                value={handoff.controlled_task_authorization.target_journey_version_id}
              />
              <input
                type="hidden"
                name="target_journey_stage_version_id"
                value={handoff.controlled_task_authorization.target_journey_stage_version_id}
              />
              <input
                type="hidden"
                name="target_task_version_id"
                value={handoff.controlled_task_authorization.target_task_version_id}
              />
              <button type="submit">本人确认进入受控训练</button>
            </form>
          </div>
        ) : handoff.acceptance_status === "ALREADY_ACCEPTED" && handoff.acceptance ? (
          <div className="handoff-card">
            <div>
              <span className="handoff-owner-label">本人确认事实</span>
              <strong>已确认，受控任务已创建</strong>
            </div>
            <p>
              确认时间 {formatDate.format(new Date(handoff.acceptance.accepted_at))}；
              Outcome 与 Handoff 保持不可变。
            </p>
            <a href={`/app/tasks/${handoff.acceptance.target_assignment_id}`}>
              查看新手村受控任务
            </a>
          </div>
        ) : handoff.acceptance_status === "AUTHORIZATION_REQUIRED" ? (
          <p className="status-meta">
            下一训练阶段 READY 决定已记录，但尚无当前有效的受控任务授权；系统不会自动分配任务。
          </p>
        ) : null}
      </section>

      <details className="panel result-section result-proof">
        <summary>查看通知与过程记录</summary>
        <section aria-labelledby="notification-title">
          <p className="section-label">05 · 通知状态</p>
          <h2 id="notification-title">核心结果不依赖通知</h2>
          <div className={`notification-state notification-${result.notification.status.toLowerCase()}`}>
            <strong>{result.notification.status}</strong>
            <p>{result.notification.display_status}</p>
          </div>
          <p className="notification-disclaimer">
            {notificationEvidence}
            {result.notification.attempt_count > 0 ? ` 已记录 ${result.notification.attempt_count} 次投递尝试。` : ""}
          </p>
        </section>

        <section aria-labelledby="timeline-title">
          <p className="section-label">06 · 不可变时间线</p>
          <h2 id="timeline-title">从提交到交接</h2>
          <ol className="result-timeline">
            {timeline.items.map((item) => {
              const detail = timelineDetail(item.event_type, item.details);
              return (
                <li key={item.item_id}>
                  <span className="timeline-dot" aria-hidden="true" />
                  <div>
                    <time dateTime={item.occurred_at}>{formatDate.format(new Date(item.occurred_at))}</time>
                    <h3>{item.title}</h3>
                    {detail ? <p>{detail}</p> : null}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      </details>
    </article>
  );
}
