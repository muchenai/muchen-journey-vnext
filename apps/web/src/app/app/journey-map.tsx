import Link from "next/link";

import { JourneyProgress } from "@/lib/server/api";

const KIND_LABELS = {
  DAY_0: "启程",
  TREASURE: "宝藏",
  ASSESSMENT: "评测",
} as const;

const STATUS_LABELS = {
  COMPLETED: "已完成",
  CURRENT: "当前阶段",
  LOCKED: "未开放",
} as const;

const ROUTE_LABELS: Record<string, string> = {
  "DAY-0": "启程",
  "TRE-001-COMPANY-VALUES": "公司价值",
  "TRE-002-AI-DATA-BASICS": "AI 与模型",
  "TRE-003-PROJECT-AWARENESS": "项目认知",
  "TRE-004-DELIVERY-FIT": "交付边界",
  "ASM-001-RULE-BREAKDOWN": "规则拆解",
  "ASM-002-MODEL-JUDGEMENT": "模型判断",
  "ASM-003-DATA-CONSTRUCTION": "数据构造",
};

const ROUTE_POINTS = {
  wide: [
    [60, 235], [200, 175], [340, 220], [485, 145],
    [630, 195], [785, 125], [940, 165], [1070, 95],
  ],
  narrow: [
    [55, 55], [180, 105], [300, 60], [270, 185],
    [145, 220], [55, 305], [175, 380], [300, 330],
  ],
} as const;

type RoutePoint = readonly [number, number];

function RouteMapSvg({
  journey,
  points,
  variant,
}: {
  journey: JourneyProgress;
  points: readonly RoutePoint[];
  variant: "wide" | "narrow";
}) {
  const viewBox = variant === "wide" ? "0 0 1120 320" : "0 0 360 450";

  return (
    <svg
      className={`journey-route-map journey-route-map-${variant}`}
      viewBox={viewBox}
      aria-hidden="true"
    >
      <polyline points={points.map((point) => point.join(",")).join(" ")} />
      {points.slice(0, journey.nodes.length).map(([x, y], index) => {
        const node = journey.nodes[index];
        const hint = `${KIND_LABELS[node.stage_kind]} · ${node.short_description}`;
        const stateClass = `route-node-visual-${node.status.toLowerCase()}`;
        const isAssessment = node.stage_kind === "ASSESSMENT";
        const isCurrent = node.status === "CURRENT";
        const contents = (
          <>
            <title>{hint}</title>
            {node.status !== "LOCKED" ? (
              <circle className="route-node-hit-area" r={isCurrent ? 32 : 28} />
            ) : null}
            {isAssessment ? (
              <rect
                className="route-node-orb"
                x={isCurrent ? -17 : -10}
                y={isCurrent ? -17 : -10}
                width={isCurrent ? 34 : 20}
                height={isCurrent ? 34 : 20}
                rx={isCurrent ? 7 : 4}
              />
            ) : (
              <circle className="route-node-orb" r={isCurrent ? 17 : 10} />
            )}
            <text className="route-node-label" textAnchor="middle" y={isCurrent ? 43 : 36}>
              {ROUTE_LABELS[node.stable_key] ?? node.title}
            </text>
          </>
        );

        return node.status !== "LOCKED" ? (
          <g
            className="route-node-anchor"
            data-route-index={index}
            key={node.stable_key}
            transform={`translate(${x} ${y})`}
          >
            <a
              className={`route-node-visual route-node-link ${stateClass}`}
              href={`/app/tasks/${node.assignment_id}`}
            >
              {contents}
            </a>
          </g>
        ) : (
          <g
            className={`route-node-anchor route-node-visual ${stateClass}`}
            data-route-index={index}
            key={node.stable_key}
            transform={`translate(${x} ${y})`}
          >
            {contents}
          </g>
        );
      })}
    </svg>
  );
}

export function JourneyMap({ journey }: { journey: JourneyProgress }) {
  const version = journey.title.match(/(?:^|\s·\s)(V\d+)$/i)?.[1] ?? null;
  const displayTitle = journey.title
    .replace(/^Muchen Journey\s*/i, "")
    .replace(/\s*·\s*V\d+$/i, "")
    .trim() || journey.title;

  return (
    <section className="journey-map" aria-labelledby="journey-map-title">
      <header className="journey-map-heading">
        <div>
          <p className="journey-whisper">It&apos;s a long game.</p>
          <h1 id="journey-map-title" aria-label={journey.title}>
            {displayTitle}
            {version ? <small>{version}</small> : null}
          </h1>
        </div>
        <strong aria-label={`已完成 ${journey.completed_stages} / ${journey.total_stages} 站`}>
          {journey.completed_stages}<span>/ {journey.total_stages}</span>
        </strong>
      </header>
      <div className="journey-route-canvas">
        <RouteMapSvg journey={journey} points={ROUTE_POINTS.wide} variant="wide" />
        <RouteMapSvg journey={journey} points={ROUTE_POINTS.narrow} variant="narrow" />
        <ol className="journey-route-accessible" aria-label="探索营阶段进度">
          {journey.nodes.map((node) => {
            const label = `${STATUS_LABELS[node.status]}：${node.title}。${node.short_description}`;
            return (
              <li key={node.stable_key}>
                {node.status !== "LOCKED" ? (
                  <Link href={`/app/tasks/${node.assignment_id}`}>{label}</Link>
                ) : label}
              </li>
            );
          })}
        </ol>
      </div>
      <p className="journey-map-hint">触碰路标，看见这一站。</p>
    </section>
  );
}
