import Link from "next/link";

import { FactLabel } from "@/app/human-experience";
import { JOURNEY_MODULES } from "@/lib/journey-program";
import type { LearnerEnrollment } from "@/lib/server/api";

function normalizedKey(value: string): string {
  return value.toLowerCase().replaceAll("_", "-");
}

export function JourneyProgramOverview({
  currentAction,
  currentJourneyKey,
  enrollments,
}: {
  currentAction: string;
  currentJourneyKey?: string | null;
  enrollments: LearnerEnrollment[];
}) {
  const currentModule = currentJourneyKey
    ? JOURNEY_MODULES.find(
      (module) => normalizedKey(module.runtimeKey) === normalizedKey(currentJourneyKey),
    )
    : undefined;
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
          <strong>{currentModule?.name ?? "状态待确认"}</strong>
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
          const isCompleted = enrollment?.status === "COMPLETED";
          return (
            <li
              className={isAssigned ? "is-current" : "is-building"}
              key={module.key}
            >
              <div className="program-module-index">{String(module.order).padStart(2, "0")}</div>
              <div className="program-module-copy">
                <p>{module.role === "CROSS_CUTTING_RESULT" ? "贯穿全程" : `第 ${module.order} 站`}</p>
                <h2>{module.name}</h2>
                <strong>{module.shortName}</strong>
                <span>{module.question}</span>
                <p className="program-module-binding">
                  <FactLabel kind="system" />
                  {isCompleted
                    ? "已完成 · 可回看"
                    : isAssigned
                      ? "进行中 · 正式任务已分配"
                      : "未分配 · 当前不可启动"}
                </p>
                <small>
                  内容包 v{module.contentBinding.version} · {module.contentBinding.taskVersionCount} 个固定任务版本
                </small>
              </div>
              <Link
                href={
                  isAssigned && enrollment
                    ? `/app?enrollment_id=${enrollment.id}`
                    : `/app/maps/${module.key}`
                }
              >
                {isCompleted
                  ? "查看已完成结果"
                  : isAssigned
                    ? "进入已分配任务"
                    : "查看开放条件与数据边界"}
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
