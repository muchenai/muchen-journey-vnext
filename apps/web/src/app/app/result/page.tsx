import { learnerPageRequest, Result, Timeline } from "@/lib/server/api";

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

const admissionLabels: Record<string, string> = {
  ADMIT: "准入下一阶段",
  DEFER: "暂缓，补充观察",
  NOT_ADMIT: "本次不准入",
};

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

export default async function ResultPage() {
  const [result, timeline] = await Promise.all([
    learnerPageRequest<Result>("/api/v1/me/result"),
    learnerPageRequest<Timeline>("/api/v1/me/timeline?limit=100"),
  ]);
  const notificationEvidence = result.notification.external_delivery_confirmed
    ? "飞书服务已确认接受通知请求。"
    : result.notification.delivery_scope === "FEISHU"
      ? "尚无飞书服务回执；结果仍以本页为准。"
      : "本地测试记录不代表外部送达。";
  return (
    <article className="result-page">
      <header className="panel result-hero">
        <div className="completion-orbit" aria-hidden="true"><i /><i /><i /></div>
        <p className="journey-whisper">The journey continues.</p>
        <p className="result-kicker"><span aria-hidden="true">✓</span> 已完成</p>
        <h1>这段旅程，走完了。</h1>
        <p className="lede">{result.summary}</p>
      </header>

      <section className="panel result-section" aria-labelledby="decision-layers-title">
        <p className="section-label">01 · 结论分层</p>
        <h2 id="decision-layers-title">完成不等于自动准入</h2>
        <div className="decision-layer-grid">
          <article>
            <span className="material-status complete">学习完成</span>
            <strong>{result.learning_completion.completed_stages} / {result.learning_completion.total_stages} 站</strong>
          </article>
          <article>
            <span className="material-status complete">Reviewer 结论</span>
            <strong>探索营通过</strong>
            <p>{result.reviewer_conclusion.overall_feedback}</p>
          </article>
          <article>
            <span className="material-status">系统建议 · 非决定</span>
            <strong>
              {result.system_recommendation.status === "RECORDED"
                ? `${result.system_recommendation.recommendation_tier} 档 · ${admissionLabels[result.system_recommendation.recommended_decision ?? ""] ?? "—"}`
                : "等待 Operator 录入人工观察"}
            </strong>
          </article>
          <article>
            <span className={`material-status ${result.operator_admission.status === "DECIDED" ? "complete" : ""}`}>Operator 人工准入</span>
            <strong>
              {result.operator_admission.status === "DECIDED"
                ? admissionLabels[result.operator_admission.decision ?? ""]
                : "尚未作出"}
            </strong>
            <p>{result.operator_admission.decision_reason ?? "完成探索营后，由 Operator 独立作出不可变结论。"}</p>
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
                <h3>{evaluation.stage_title.replace(/^能力评测[一二三]：/, "")}</h3>
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
      </section>

      <section className="panel result-section" aria-labelledby="handoff-title">
        <p className="section-label">03 · 唯一下一步</p>
        <h2 id="handoff-title">{result.handoff.next_step_title}</h2>
        <div className="handoff-card">
          <div>
            <span className="handoff-owner-label">交接责任人</span>
            <strong>{result.handoff.owner_display_name}</strong>
          </div>
          <p>{result.handoff.instructions}</p>
        </div>
      </section>

      <details className="panel result-section result-proof">
        <summary>查看通知与过程记录</summary>
        <p className="status-meta">
          结果生成于 <time dateTime={result.created_at}>{formatDate.format(new Date(result.created_at))}</time>
        </p>
        <section aria-labelledby="notification-title">
          <h2 id="notification-title">通知状态</h2>
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
          <h2 id="timeline-title">过程记录</h2>
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
