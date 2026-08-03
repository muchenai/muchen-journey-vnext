import Link from "next/link";

import { JourneyProgress } from "@/lib/server/api";

const KIND_LABELS = {
  DAY_0: "启程",
  TREASURE: "宝藏",
  ASSESSMENT: "评测",
} as const;

const ROUTE_LABELS: Record<string, string> = {
  "DAY-0": "启程",
  "TRE-001-COMPANY-VALUES": "公司价值",
  "TRE-002-AI-DATA-BASICS": "AI 与模型",
  "TRE-003-PROJECT-AWARENESS": "项目认知",
  "TRE-004-DELIVERY-FIT": "交付边界",
  "ASM-001-RULE-BREAKDOWN": "规则拆解",
  "ASM-002-MODEL-JUDGEMENT": "模型判断",
  "ASM-003-BOUNDARY-ESCALATION": "边界提报",
};

export function JourneyMap({ journey }: { journey: JourneyProgress }) {
  return (
    <section className="journey-map" aria-labelledby="journey-map-title">
      <header className="journey-map-heading">
        <div>
          <p className="journey-whisper">It&apos;s a long game.</p>
          <h1 id="journey-map-title">{journey.title}</h1>
        </div>
        <strong aria-label={`已完成 ${journey.completed_stages} / ${journey.total_stages} 站`}>
          {journey.completed_stages}<span>/ {journey.total_stages}</span>
        </strong>
      </header>
      <ol className="journey-route" aria-label="探索营阶段进度">
        {journey.nodes.map((node) => {
          const hint = `${KIND_LABELS[node.stage_kind]} · ${node.short_description}`;
          const nodeBody = (
            <>
              <span className="route-node-orb" aria-hidden="true" />
              <span className="route-node-label">
                {ROUTE_LABELS[node.stable_key] ?? node.title}
              </span>
            </>
          );
          return (
            <li
              className={`route-node route-node-${node.status.toLowerCase()}`}
              key={node.stable_key}
            >
              {node.status === "CURRENT" ? (
                <Link
                  className="route-node-control"
                  href={`/app/tasks/${node.assignment_id}`}
                  data-hint={hint}
                  aria-label={`当前阶段：${node.title}。${node.short_description}`}
                >
                  {nodeBody}
                </Link>
              ) : (
                <span
                  className="route-node-control"
                  data-hint={hint}
                  tabIndex={0}
                  aria-label={`${node.status === "COMPLETED" ? "已完成" : "未开放"}：${node.title}。${node.short_description}`}
                >
                  {nodeBody}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="journey-map-hint">触碰路标，看见这一站。</p>
    </section>
  );
}
