import Link from "next/link";
import { notFound } from "next/navigation";

import { getJourneyModule, JOURNEY_MODULES } from "@/lib/journey-program";

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
          <span>{journeyModule.status === "CURRENT" ? "当前阶段" : "内容 Gate 待通过"}</span>
          <p>这一站带走</p>
          <strong>{journeyModule.output}</strong>
        </aside>
      </header>

      <section className="module-next-action" aria-labelledby="module-next-action-title">
        <div>
          <p>进入这一站时，只做一件事</p>
          <h2 id="module-next-action-title">{journeyModule.nextAction}</h2>
          <span>内容依据：{journeyModule.source}</span>
        </div>
        {journeyModule.status === "CURRENT" ? (
          <Link className="button primary" href="/app">继续当前任务 →</Link>
        ) : (
          <strong>尚未开放正式任务 · 不会创建虚构任务</strong>
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
