import Link from "next/link";

import { JOURNEY_MODULES } from "@/lib/journey-program";
import type { LearnerEnrollment } from "@/lib/server/api";

function normalizedKey(value: string): string {
  return value.toLowerCase().replaceAll("_", "-");
}

export function JourneyProgramOverview({
  currentAction,
  enrollments,
}: {
  currentAction: string;
  enrollments: LearnerEnrollment[];
}) {
  return (
    <section className="program-overview" aria-labelledby="program-overview-title">
      <header className="program-overview-heading">
        <div>
          <p className="journey-whisper">Muchen Journey · 2026-09-01 四模块受控首发</p>
          <h1 id="program-overview-title">做完当前一步，再看四个模块</h1>
          <p>
            本次受控首发只开放四个模块入口。每一站都从真实问题出发，经过实操、证据和真人确认，形成可复核结果包。
          </p>
        </div>
        <aside aria-label="当前位置">
          <span>你现在在</span>
          <strong>探索营</strong>
          <small>{currentAction}</small>
        </aside>
      </header>
      <ol className="program-module-grid">
        {JOURNEY_MODULES.map((module) => {
          const enrollment = enrollments.find(
            (item) =>
              item.journey_stable_key
              && normalizedKey(item.journey_stable_key) === normalizedKey(module.runtimeKey),
          );
          const isAssigned = Boolean(
            enrollment && ["ACTIVE", "COMPLETED"].includes(enrollment.status),
          );
          return (
            <li
              className={isAssigned || module.status === "CURRENT" ? "is-current" : "is-building"}
              key={module.key}
            >
              <div className="program-module-index">{String(module.order).padStart(2, "0")}</div>
              <div className="program-module-copy">
                <p>{module.role === "CROSS_CUTTING_RESULT" ? "贯穿全程" : `第 ${module.order} 站`}</p>
                <h2>{module.name}</h2>
                <strong>{module.shortName}</strong>
                <span>{module.question}</span>
              </div>
              <Link
                href={
                  isAssigned && enrollment
                    ? `/app?enrollment_id=${enrollment.id}`
                    : `/app/maps/${module.key}`
                }
              >
                {enrollment?.status === "COMPLETED"
                  ? "查看已完成结果"
                  : isAssigned
                    ? "进入已分配任务"
                    : "查看模块范围与开放条件"}
              </Link>
            </li>
          );
        })}
      </ol>
      <p className="program-governance-note">
        受控首发不等于完整产品发布。正式能力结果只来自实操证据和真人 Gate；AI 建议、积分和自证都不会单独产生人才结论。
      </p>
    </section>
  );
}
