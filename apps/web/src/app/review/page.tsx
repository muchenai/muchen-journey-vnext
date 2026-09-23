import Link from "next/link";

import { FactLabel } from "@/app/human-experience";
import { LiveStatusSignal } from "@/app/live-status-signal";
import { formatProductDateTime } from "@/lib/date-time";
import { identityPageRequest, ReviewHistory, ReviewItem } from "@/lib/server/api";

export const dynamic = "force-dynamic";

function QueueSection({ id, title, description, items }: {
  id: string; title: string; description: string; items: ReviewItem[];
}) {
  return (
    <section className="review-history" aria-labelledby={id}>
      <div className="section-heading-row">
        <div><h2 id={id}>{title}</h2><p className="status-meta">{description}</p></div>
        <span className="badge">待处理 {items.length} 项</span>
      </div>
      {items.length === 0 ? <p className="status-meta">当前没有待处理记录。</p> : (
        <ol className="queue">
          {items.map((item, index) => (
            <li key={item.id}>
              <Link className="queue-item" href={`/review/${item.id}`}>
                <div className="section-heading-row">
                  <span className="badge">优先级 {index + 1} · {item.status === "IN_REVIEW" ? "评阅中" : "待开始"}</span>
                  <span className={`material-status ${item.material_status.toLowerCase()}`}>{item.material_status === "COMPLETE" ? "材料完整" : "材料不完整"}</span>
                </div>
                <strong className="queue-title">{item.learner_name} · {item.task_title}</strong>
                <span>{item.journey_title ?? "固定任务"}</span>
                <span>{item.priority_reason}</span>
                <span className="queue-meta">任务 V{item.task_version} · 固定提交 V{item.submission_version_no} · 提交于 {formatProductDateTime(item.submitted_at)}</span>
                <span className="queue-meta">首次反馈配置 {item.feedback_sla_business_days} 个工作日；未绑定营业日历，不计算精确逾期</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function HistorySection({ title, history, cursorName }: {
  title: string; history: ReviewHistory; cursorName: "formal_history_cursor" | "coaching_history_cursor";
}) {
  return (
    <section className="review-history">
      <div className="section-heading-row"><h3>{title}</h3><span className="badge">本页 {history.items.length} 条</span></div>
      {history.items.length === 0 ? <p className="status-meta">当前页没有已完成记录。</p> : (
        <ol className="queue">
          {history.items.map((item) => (
            <li key={item.id}><Link className="queue-item" href={`/review/${item.id}`}>
              <div className="section-heading-row"><strong>{item.learner_name} · {item.task_title}</strong>
                  <span className={`history-decision ${item.decision === "PASS" ? "pass" : "revision"}`}>{item.decision === "PASS" ? (item.review_kind === "FORMAL_EVALUATION" ? "已通过" : "已达到学习目标") : item.decision === "REVISION_REQUIRED" ? "要求修订" : "历史版本 · 未评阅"}</span>
              </div>
              <span>{item.journey_title ?? "固定任务"}</span>
              <span className="queue-meta">固定提交 V{item.submission_version_no} · 定稿于 {formatProductDateTime(item.finalized_at)}</span>
            </Link></li>
          ))}
        </ol>
      )}
      {history.next_cursor ? <Link className="button secondary" href={`/review?${cursorName}=${encodeURIComponent(history.next_cursor)}`}>查看更早记录</Link> : null}
    </section>
  );
}

export default async function ReviewQueuePage({ searchParams }: {
  searchParams: Promise<{ finalized?: string; formal_history_cursor?: string; coaching_history_cursor?: string }>;
}) {
  const query = await searchParams;
  const formalHistoryPath = `/api/v1/reviews/history?kind=FORMAL_EVALUATION${query.formal_history_cursor ? `&cursor=${encodeURIComponent(query.formal_history_cursor)}` : ""}`;
  const coachingHistoryPath = `/api/v1/reviews/history?kind=LEARNING_COACHING${query.coaching_history_cursor ? `&cursor=${encodeURIComponent(query.coaching_history_cursor)}` : ""}`;
  const [formalQueue, coachingQueue, formalHistory, coachingHistory] = await Promise.all([
    identityPageRequest<{ items: ReviewItem[] }>("/api/v1/reviews?kind=FORMAL_EVALUATION", "REVIEWER"),
    identityPageRequest<{ items: ReviewItem[] }>("/api/v1/reviews?kind=LEARNING_COACHING", "REVIEWER"),
    identityPageRequest<ReviewHistory>(formalHistoryPath, "REVIEWER"),
    identityPageRequest<ReviewHistory>(coachingHistoryPath, "REVIEWER"),
  ]);
  const allItems = [...formalQueue.items, ...coachingQueue.items];
  const statusKey = allItems.map((item) => `${item.id}:${item.status}:${item.submission_version_no}`).join("|");

  return (
    <section className="content-narrow review-queue-page">
      <p className="eyebrow">主管工作台</p><h1>评测与辅导</h1>
      <p className="lede">只显示当前组织内明确分配或合法委派给你的固定提交版本。</p>
      <div className="review-queue-boundary"><FactLabel kind="system" />
        <p><strong>正式评测</strong>会形成 Evaluation/Human Gate；<strong>宝藏辅导</strong>只形成辅导事实，不影响旅程推进、结营或准入。</p>
        <p>反馈 SLA 只显示配置值；未绑定营业日历时不虚构精确逾期时间。</p>
        <p><strong>容量：未获批准，无法计算。</strong> 主备与升级仍由运营依据固定 Reviewer 绑定处理。</p>
      </div>
      <LiveStatusSignal statusKey={statusKey} active title={allItems.length ? `有 ${allItems.length} 项等待处理` : "当前没有新提交"} detail="页面会自动检查新提交。" changedMessage="有新的提交或状态变化，队列已更新。" />
      {query.finalized ? <p className="success-text" role="status">审核结果提交成功，刷新后仍会保留。</p> : null}
      <QueueSection id="formal-review-title" title="正式评测" description="三项评测；结论进入 Evaluation，并按既有正式状态机处理。" items={formalQueue.items} />
      <QueueSection id="coaching-review-title" title="宝藏辅导" description="四个宝藏；可确认达到目标或要求修订，但不阻塞后续旅程。" items={coachingQueue.items} />
      <p className="status-meta">Day 0 仍由 Learner 自证完成，不进入评阅。</p>
      <section aria-labelledby="review-history-title"><h2 id="review-history-title">已完成评阅</h2>
        <HistorySection title="正式评测历史" history={formalHistory} cursorName="formal_history_cursor" />
        <HistorySection title="宝藏辅导历史" history={coachingHistory} cursorName="coaching_history_cursor" />
      </section>
    </section>
  );
}
