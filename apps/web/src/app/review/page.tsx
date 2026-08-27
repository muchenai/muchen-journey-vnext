import Link from "next/link";

import { FactLabel } from "@/app/human-experience";
import { identityPageRequest, ReviewItem } from "@/lib/server/api";

export const dynamic = "force-dynamic";

function formatWait(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default async function ReviewQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ finalized?: string }>;
}) {
  const query = await searchParams;
  const queue = await identityPageRequest<{ items: ReviewItem[] }>(
    "/api/v1/reviews",
    "REVIEWER",
  );
  const checkedAt = new Date();
  return (
    <section className="content-narrow review-queue-page">
      <p className="eyebrow">主管工作台</p>
      <h1>现在先评谁？</h1>
      <p className="lede">只显示明确分配给当前主管、且属于当前组织的待处理评审。</p>
      <div className="review-queue-boundary">
        <FactLabel kind="system" />
        <p><strong>容量：未获批准，无法计算。</strong> 页面不会用待审数量猜测 Reviewer 是否超载。</p>
        <p>主备与升级：当前 Reviewer 队列接口未提供批准的替补映射；需要交接时请保留 Review ID 并联系运营核对绑定。</p>
        <p>利益冲突：当前仅能证明任务已分配给本人，自动回避检查为 NOT_EVALUATED，不宣称“无冲突”。</p>
      </div>
      {query.finalized ? (
        <p className="success-text" role="status">
          {query.finalized === "approved" ? "通过结论已定稿，任务已完成。" : "修订结论已定稿，新人已进入修订状态。"}
        </p>
      ) : null}
      {queue.items.length === 0 ? (
        <div className="notice">
          <strong>查询已成功：当前没有待处理评审</strong>
          <p>这不是数据未加载，也不表示其他 Reviewer 或模块的队列为 0。</p>
          <small>最近检查：{formatWait(checkedAt.toISOString())} · 范围：当前组织、当前 Reviewer、ASSIGNED/IN_REVIEW</small>
        </div>
      ) : (
        <>
          <Link className="button primary" href={`/review/${queue.items[0].id}`}>
            打开最高优先级待审提交
          </Link>
          <p className="status-meta">最近检查：{formatWait(checkedAt.toISOString())} · 排序来自服务端队列</p>
          <ol className="queue">
          {queue.items.map((item, index) => (
            <li key={item.id}>
              <Link className="queue-item" href={`/review/${item.id}`}>
                <div className="section-heading-row">
                  <span className="badge">优先级 {index + 1} · {item.status === "IN_REVIEW" ? "评审中" : "待开始"}</span>
                  <span className={`material-status ${item.material_status.toLowerCase()}`}>
                    {item.material_status === "COMPLETE" ? "材料完整" : "材料不完整"}
                  </span>
                </div>
                <strong className="queue-title">{item.learner_name} · {item.task_title}</strong>
                <span>{item.priority_reason}</span>
                <span className="queue-meta">
                  任务 V{item.task_version} · 提交 V{item.submission_version_no} · 返工 {item.revision_count} 次 · 提交于 {formatWait(item.submitted_at)}
                </span>
                <span className="queue-meta">首次反馈配置 {item.feedback_sla_business_days} 个工作日；未绑定营业日历，不计算逾期 · {item.sensitivity} · {item.audience}</span>
                <span className="queue-meta">冲突检查 {item.conflict_status} · 分配于 {formatWait(item.assigned_at)}</span>
              </Link>
            </li>
          ))}
          </ol>
        </>
      )}
    </section>
  );
}
