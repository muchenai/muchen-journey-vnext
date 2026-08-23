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
    [90, 70], [255, 170], [90, 270], [255, 370],
    [90, 470], [255, 570], [90, 670], [255, 770],
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
  const viewBox = variant === "wide" ? "0 0 1120 320" : "0 0 360 880";

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

        return (
          <g
            className={`route-node-visual ${stateClass}`}
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

export function JourneyMap({
  journey,
  current,
}: {
  journey: JourneyProgress;
  current: {
    position: number;
    title: string;
    reason: string;
    href: string | null;
    actionLabel: string | null;
  };
}) {
  return (
    <section className="journey-map" aria-labelledby="journey-map-title">
      <span className="journey-map-world" aria-hidden="true" />
      <header className="journey-map-heading">
        <div>
          <p className="journey-whisper">探索营 · Map 01 / 05</p>
          <h1 id="journey-map-title">你现在只走这一站</h1>
        </div>
        <strong aria-label={`已完成 ${journey.completed_stages} / ${journey.total_stages} 站`}>
          {journey.completed_stages}<span>/ {journey.total_stages}</span>
        </strong>
      </header>
      <article className="journey-current-mission">
        <p>当前任务 · 第 {current.position + 1} 站</p>
        <h2>{current.title}</h2>
        <span>{current.reason}</span>
        {current.href && current.actionLabel ? (
          <Link className="button primary" href={current.href}>{current.actionLabel}<b aria-hidden="true">→</b></Link>
        ) : (
          <strong className="journey-waiting">等待下一步开放</strong>
        )}
      </article>
      <div className="journey-route-canvas">
        <RouteMapSvg journey={journey} points={ROUTE_POINTS.wide} variant="wide" />
        <RouteMapSvg journey={journey} points={ROUTE_POINTS.narrow} variant="narrow" />
        <ol className="journey-route-accessible" aria-label="探索营阶段进度">
          {journey.nodes.map((node) => {
            const label = `${STATUS_LABELS[node.status]}：${node.title}。${node.short_description}`;
            return (
              <li key={node.stable_key}>{label}</li>
            );
          })}
        </ol>
      </div>
      <p className="journey-map-hint">暖金色路标是当前位置；方形路标是能力评测。</p>
    </section>
  );
}
