import { randomUUID } from "node:crypto";
import Link from "next/link";

import { FactLabel } from "@/app/human-experience";
import { formatProductDateTime } from "@/lib/date-time";
import { identityPageRequest, ReviewDetail } from "@/lib/server/api";
import { ReviewWorkbench } from "./review-workbench";

export const dynamic = "force-dynamic";

const RATING_LABELS = { MEETS: "达标", NEEDS_WORK: "待改进" } as const;
const DECISION_LABELS = { APPROVE: "通过", REQUEST_REVISION: "要求修订" } as const;
const HTTPS_URL = /(https:\/\/[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+)/gu;
const TRAILING_URL_PUNCTUATION = /[),.;!?，。；！？、）】》]+$/u;

function submissionWithSafeLinks(value: string) {
  return value.split(HTTPS_URL).map((part, index) => {
    if (!part.startsWith("https://")) return part;
    const trailing = part.match(TRAILING_URL_PUNCTUATION)?.[0] ?? "";
    const href = trailing ? part.slice(0, -trailing.length) : part;
    const hostname = new URL(href).hostname;
    const isFeishuHost = hostname === "feishu.cn"
      || hostname.endsWith(".feishu.cn")
      || hostname === "larksuite.com"
      || hostname.endsWith(".larksuite.com");
    if (!isFeishuHost) return part;
    return (
      <span key={`${href}-${index}`}>
        <a href={href} target="_blank" rel="noreferrer">打开 Learner 的飞书文档 ↗</a>
        {trailing}
      </span>
    );
  });
}

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ reviewId: string }>;
  searchParams: Promise<{ started?: string; finalized?: string }>;
}) {
  const { reviewId } = await params;
  const query = await searchParams;
  const review = await identityPageRequest<ReviewDetail>(
    `/api/v1/reviews/${encodeURIComponent(reviewId)}`,
    "REVIEWER",
  );
  const rubricTitles = new Map(
    review.rubric.dimensions.map((dimension) => [dimension.dimension_key, dimension.title]),
  );

  return (
    <article className="panel review-detail">
      <Link className="back-link" href="/review">← 返回评审队列</Link>
      <p className="eyebrow">
        固定任务 V{review.task_version} · 固定提交 V{review.submission_version_no}
      </p>
      <h1>{review.learner_name} · {review.task_title}</h1>
      <p className="status-meta">
        {review.review_kind === "LEARNING_COACHING"
          ? "宝藏辅导 · 只形成辅导反馈，不影响旅程推进、结营或准入"
          : "正式评测 · 结论进入 Evaluation / Human Gate"}
      </p>
      <div className="review-status-row">
        <span className="badge">{review.status === "IN_REVIEW" ? "评审中" : review.status === "FINALIZED" ? "已定稿" : review.status === "SUPERSEDED" ? "已被新版本替代" : "待开始"}</span>
        <span>{review.priority_reason}</span>
        <span>分配于 {formatProductDateTime(review.assigned_at)}</span>
      </div>
      <p className="status-meta">
        固定 SubmissionVersion <code>{review.submission_version_id}</code> · Rubric V{review.rubric.version} · 冲突检查 {review.conflict_status}
      </p>
      {query.started === "yes" ? (
        <p className="success-text" role="status">{review.review_kind === "LEARNING_COACHING" ? "辅导评阅已开始；Learner 任务状态未改变。" : "评审已开始，任务状态已同步为评审中。"}</p>
      ) : null}
      {query.finalized && (review.evaluation || review.coaching_feedback) ? (
        <p className="success-text" role="status">
          {query.finalized === "approved"
            ? "审核结果提交成功：通过结论已定稿，刷新后仍会保留。"
            : "审核结果提交成功：修订结论已定稿，刷新后仍会保留。"}
        </p>
      ) : null}

      <section className="review-section" aria-labelledby="task-context-title">
        <h2 id="task-context-title">任务与完成标准</h2>
        <p>{review.task_purpose}</p>
        <ul className="checklist">
          {review.completion_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
        </ul>
      </section>

      <section className="review-section" aria-labelledby="materials-title">
        <div className="section-heading-row">
          <h2 id="materials-title">材料完整性</h2>
          <span className={`material-status ${review.materials.status.toLowerCase()}`}>
            {review.materials.status === "COMPLETE" ? "材料完整" : "材料不完整"}
          </span>
        </div>
        <h3>本任务要求的交付</h3>
        <ul className="checklist">
          {review.materials.required_deliverables.map((deliverable) => (
            <li key={deliverable}>{deliverable}</li>
          ))}
        </ul>
        {review.materials.missing_items.length > 0 ? (
          <div className="inline-error" role="alert">
            <strong>缺失或不可用</strong>
            <ul>
              {review.materials.missing_items.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {review.materials.attachments.length > 0 ? (
          <ul className="attachment-list">
            {review.materials.attachments.map((attachment) => (
              <li key={attachment.id}>
                <span>
                  <strong>{attachment.original_filename}</strong>
                  <small>{attachment.content_type} · {Math.ceil(attachment.size_bytes / 1024)} KiB</small>
                </span>
                <span className="badge">{attachment.status} · {attachment.scan_status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="status-meta">此固定版本没有附件；交付内容位于下方正文。</p>
        )}
      </section>

      <section className="review-section" aria-labelledby="submission-title">
        <FactLabel kind="completion" />
        <h2 id="submission-title">固定提交正文</h2>
        <p className="status-meta">该正文属于 SubmissionVersion {review.submission_version_no}，评审不会修改它。</p>
        <p className="status-meta">
          <FactLabel kind="ai" />{" "}
          AI 披露：{review.submission_ai_use.used
            ? `已使用（${review.submission_ai_use.purpose}）；只作建议`
            : "未使用"}
        </p>
        <div className="submission">{submissionWithSafeLinks(review.submission_body)}</div>
      </section>

      <section className="review-section" aria-labelledby="ai-advisory-title">
        <FactLabel kind="ai" />
        <h2 id="ai-advisory-title">AI 自查建议</h2>
        {review.ai_advisory ? (
          <>
            <p>已生成不可变建议记录；仅供 Reviewer 参考，不能改变任何正式状态。</p>
            <p className="status-meta">模型 {review.ai_advisory.model_version} · Prompt {review.ai_advisory.prompt_version} · 策略 {review.ai_advisory.policy_version}</p>
            <p className="status-meta">输入摘要 SHA-256 <code>{review.ai_advisory.input_sha256}</code> · 生成于 {formatProductDateTime(review.ai_advisory.generated_at)}</p>
            <pre className="submission">{JSON.stringify(review.ai_advisory.result, null, 2)}</pre>
          </>
        ) : <p className="status-meta">AI 自查未运行 / 当前不可用；未生成空记录或评价。</p>}
      </section>

      <details className="fixed-references">
        <summary>查看固定引用</summary>
        <dl>
          <div><dt>Assignment</dt><dd><code>{review.assignment_id}</code></dd></div>
          <div><dt>Submission</dt><dd><code>{review.submission_id}</code></dd></div>
          <div><dt>SubmissionVersion</dt><dd><code>{review.submission_version_id}</code></dd></div>
        </dl>
      </details>

      <details className="fixed-references">
        <summary>查看该任务的旧提交版本（只读）</summary>
        {review.submission_history.map((version) => (
          <article className="history-version" key={version.id}>
            <h3>Version {version.version_no}</h3>
            <p className="status-meta">{formatProductDateTime(version.created_at)} · {version.review_kind ?? "未创建评阅"} · {version.review_status ?? "仅提交历史"}</p>
            <div className="submission">{submissionWithSafeLinks(version.body)}</div>
            {version.feedback ? <p>{version.feedback}</p> : null}
          </article>
        ))}
      </details>

      {review.evaluation || review.coaching_feedback ? (
        <section className="review-section evaluation-history" aria-labelledby="evaluation-title">
          <FactLabel kind="human" />
          <p className="eyebrow">只读结论历史</p>
          <h2 id="evaluation-title">{DECISION_LABELS[(review.evaluation ?? review.coaching_feedback)!.overall_decision]}</h2>
          <p className="status-meta">
            定稿于 {formatProductDateTime((review.evaluation ?? review.coaching_feedback)!.created_at)} · Review revision {(review.evaluation ?? review.coaching_feedback)!.review_revision}
          </p>
          <div className="feedback-callout">
            <strong>总体反馈</strong>
            <p>{(review.evaluation ?? review.coaching_feedback)!.overall_feedback}</p>
          </div>
          <p className="status-meta">
            Reviewer AI 披露：{(review.evaluation ?? review.coaching_feedback)!.ai_use.used
              ? `已使用（${(review.evaluation ?? review.coaching_feedback)!.ai_use.purpose}）；不替代真人决定`
              : "未使用"}
          </p>
          {review.coaching_feedback ? <p className="status-meta">此结论为非阻塞辅导反馈，不产生 Evaluation。</p> : null}
          <ol className="evaluation-list">
            {(review.evaluation ?? review.coaching_feedback)!.rubric_evaluations.map((item) => (
              <li key={item.dimension_key}>
                <div className="section-heading-row">
                  <strong>{rubricTitles.get(item.dimension_key) ?? item.dimension_key}</strong>
                  <span className="badge">{RATING_LABELS[item.rating]}</span>
                </div>
                <p>{item.feedback ?? "旧版结论未记录维度级反馈；不补写历史。"}</p>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <ReviewWorkbench
          reviewId={review.id}
          reviewKind={review.review_kind}
          revision={review.revision}
          allowedCommands={review.allowed_commands}
          materialStatus={review.materials.status}
          dimensions={review.rubric.dimensions}
          startIdempotencyKey={randomUUID()}
          finalizeIdempotencyKey={randomUUID()}
        />
      )}
      <aside className="review-governance-note">
        <h2>结论与申诉边界</h2>
        <p>{review.review_kind === "LEARNING_COACHING" ? "只有具名 Reviewer 对固定版本提交明确结论与理由后，服务端才会追加不可变辅导事实。" : "只有具名 Reviewer 提交完整 Rubric 与理由后，服务端才会追加不可变真人 Evaluation。"} AI 建议不能代签。</p>
        <p>通用高影响申诉政策尚未获批准；本页不承诺申诉入口或 SLA。已批准的下一训练阶段独立复核在学员结果页单独处理。</p>
        <p>若提交结果未知，请保留当前页面与 request ID，重新查询此 Review；不要重复点击或猜测 Evaluation 已写入。</p>
      </aside>
    </article>
  );
}
