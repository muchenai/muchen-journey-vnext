import Link from "next/link";
import { notFound } from "next/navigation";

import { ExperienceState, FactLabel } from "@/app/human-experience";
import { getJourneyModule, JOURNEY_MODULES } from "@/lib/journey-program";
import { LearnerEnrollment, learnerPageRequest } from "@/lib/server/api";

function normalizedKey(value: string): string {
  return value.toLowerCase().replaceAll("_", "-");
}

export function generateStaticParams() {
  return JOURNEY_MODULES.map((module) => ({ mapKey: module.key }));
}

export default async function JourneyModulePage({
  params,
}: {
  params: Promise<{ mapKey: string }>;
}) {
  const { mapKey } = await params;
  const journeyModule = getJourneyModule(mapKey);

  if (!journeyModule) {
    notFound();
  }

  const enrollments = await learnerPageRequest<{ items: LearnerEnrollment[] }>(
    "/api/v1/me/enrollments",
  );
  const enrollment = enrollments.items.find(
    (item) => item.journey_stable_key
      && normalizedKey(item.journey_stable_key) === normalizedKey(journeyModule.runtimeKey),
  );
  const isAssigned = Boolean(
    enrollment && ["ACTIVE", "COMPLETED"].includes(enrollment.status),
  );
  const contentBinding = journeyModule.contentBinding;

  return (
    <section className="module-page">
      <Link className="back-link" href="/app">← 返回四模块首页</Link>
      <header className="module-hero">
        <div>
          <p className="journey-whisper">
            {journeyModule.role === "CROSS_CUTTING_RESULT" ? "成长结果层" : `Journey ${String(journeyModule.order).padStart(2, "0")}`} · Owner {journeyModule.owner}
          </p>
          <h1>{journeyModule.name}</h1>
          <strong>{journeyModule.question}</strong>
          <p>{journeyModule.promise}</p>
        </div>
        <aside>
          <span>{isAssigned ? "正式任务已分配" : "受控入口 · 当前未分配"}</span>
          <p>这一站带走</p>
          <strong>{journeyModule.output}</strong>
        </aside>
      </header>

      <section className="module-binding" aria-labelledby="module-binding-title">
        <header>
          <FactLabel kind="system" />
          <h2 id="module-binding-title">进入前先核对这些绑定事实</h2>
        </header>
        <dl className="module-binding-facts">
          <div><dt>适用身份</dt><dd>已获当前模块 Enrollment 的学员</dd></div>
          <div><dt>学习输入预计</dt><dd>{contentBinding.contentEstimatedMinutes} 分钟；实操时间以固定任务版本为准</dd></div>
          <div><dt>正式产出</dt><dd>{journeyModule.output}</dd></div>
          <div><dt>Reviewer 配置</dt><dd>{contentBinding.reviewerPoolRef} · 主 Reviewer {contentBinding.primaryReviewers.join("、")} · 备用 {contentBinding.backupReviewers.join("、")}</dd></div>
          <div><dt>数据边界</dt><dd>禁止生产写入；禁止原始客户数据；AI 不得作高影响决定；保留策略 {contentBinding.dataPolicy.retentionPolicy}</dd></div>
          <div><dt>内容绑定</dt><dd>v{contentBinding.version} · {contentBinding.taskVersionCount} 个任务版本 · {contentBinding.rubricCount} 个 Rubric · 生效于 {contentBinding.effectiveAt}</dd></div>
          <div className="module-binding-hash"><dt>内容包 SHA-256</dt><dd><code>{contentBinding.packageSha256}</code></dd></div>
        </dl>
      </section>

      <section className="module-next-action" aria-labelledby="module-next-action-title">
        <div>
          <p>进入这一站时，只做一件事</p>
          <h2 id="module-next-action-title">{journeyModule.nextAction}</h2>
          <span>内容依据：{journeyModule.source}</span>
        </div>
        {isAssigned && enrollment ? (
          <Link className="button primary" href={`/app?enrollment_id=${enrollment.id}`}>
            {enrollment.status === "COMPLETED" ? "查看已完成结果" : "开始或继续本模块"} →
          </Link>
        ) : (
          <ExperienceState
            kind="locked"
            title="正式任务尚未分配"
            summary="内容包已绑定，但没有当前模块的有效 Enrollment；入口不会创建虚构任务或自动解锁。"
            knownFacts={[
              `已绑定内容包：${contentBinding.packageId}`,
              `缺失条件：当前模块 ACTIVE 或 COMPLETED Enrollment`,
              `责任 Owner：${contentBinding.ownerName}`,
            ]}
            action={{ href: "/app", label: "返回当前可行动任务" }}
          />
        )}
      </section>

      <div className="module-contract-grid">
        <article>
          <p className="section-label">人要走的闭环</p>
          <h2>从行动到结果</h2>
          <ol className="module-flow">
            {journeyModule.steps.map((step, index) => (
              <li key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </li>
            ))}
          </ol>
        </article>
        <article>
          <p className="section-label">系统必须留下什么</p>
          <h2>可复核证据</h2>
          <ul className="module-evidence-list">
            {journeyModule.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
          </ul>
        </article>
      </div>

      <section className="module-boundaries">
        <article>
          <span>必须经过的真人 Gate</span>
          <p>{journeyModule.humanGate}</p>
        </article>
        <article>
          <span>系统明确不能做</span>
          <p>{journeyModule.prohibited}</p>
        </article>
      </section>
    </section>
  );
}
