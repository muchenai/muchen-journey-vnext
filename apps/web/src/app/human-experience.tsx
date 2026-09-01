import Link from "next/link";

export const FACT_LABELS = {
  completion: "完成事实",
  human: "人工判断",
  ai: "AI 建议",
  incentive: "积分激励",
  system: "系统状态",
} as const;

const FACT_DESCRIPTIONS = {
  completion: "已发生且可以回链的行为或证据，不代表能力结论。",
  human: "具名真人依据固定证据和 Rubric 签署的判断。",
  ai: "可采纳、可拒绝的辅助信息，不会改变正式状态。",
  incentive: "独立激励记录，不作为正式进度或准入依据。",
  system: "服务端已确认的流程、权限或运行事实，不评价个人。",
} as const;

export type FactKind = keyof typeof FACT_LABELS;

export function FactLabel({ kind }: { kind: FactKind }) {
  return (
    <span className={`fact-label fact-label-${kind}`} data-fact-kind={kind}>
      {FACT_LABELS[kind]}
    </span>
  );
}

export function FactLegend() {
  return (
    <details className="fact-legend">
      <summary>这五类信息有什么不同？</summary>
      <dl>
        {(Object.keys(FACT_LABELS) as FactKind[]).map((kind) => (
          <div key={kind}>
            <dt><FactLabel kind={kind} /></dt>
            <dd>{FACT_DESCRIPTIONS[kind]}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export type ExperienceStateKind = "locked" | "empty" | "error";

export function ExperienceState({
  kind,
  title,
  summary,
  knownFacts,
  action,
}: {
  kind: ExperienceStateKind;
  title: string;
  summary: string;
  knownFacts: string[];
  action: { href: string; label: string };
}) {
  return (
    <section
      className={`experience-state experience-state-${kind}`}
      data-experience-state={kind}
      role={kind === "error" ? "alert" : undefined}
    >
      <FactLabel kind="system" />
      <h2>{title}</h2>
      <p>{summary}</p>
      <ul>
        {knownFacts.map((fact) => <li key={fact}>{fact}</li>)}
      </ul>
      <Link className="button primary" href={action.href} prefetch={false}>
        {action.label}
      </Link>
    </section>
  );
}
