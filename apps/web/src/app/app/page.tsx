import Link from "next/link";

import { logoutSession } from "@/app/actions";
import { CurrentAction, hasVNextSession, learnerPageRequest } from "@/lib/server/api";
import { JourneyMap } from "./journey-map";

export const dynamic = "force-dynamic";

export default async function LearnerHome({
  searchParams,
}: {
  searchParams: Promise<{ transition?: string }>;
}) {
  const query = await searchParams;
  const [action, hasSession] = await Promise.all([
    learnerPageRequest<CurrentAction>("/api/v1/me/current-action"),
    hasVNextSession(),
  ]);
  const opensTask = ["START_OR_CONTINUE_TASK", "REVISE_SUBMISSION"].includes(
    action.action_type,
  );
  const opensResult = action.action_type === "VIEW_RESULT_OR_HANDOFF";
  const primaryActionLabel = opensResult
    ? "查看结果"
    : action.action_type === "REVISE_SUBMISSION"
      ? "继续修订"
      : action.title === "继续这一站"
        ? "继续"
        : "开始";

  return (
    <section className={action.journey ? "learner-journey-page" : "content-narrow"}>
      {query.transition === "submitted" ? (
        <section className="journey-transition" role="status" aria-labelledby="journey-transition-title">
          <span aria-hidden="true">✓</span>
          <div>
            <p className="eyebrow">这一站已保存</p>
            <h1 id="journey-transition-title">
              {opensTask ? "下一站已解锁" : "已经交给 Reviewer"}
            </h1>
            <p>{opensTask ? "路线已经更新，继续从当前路标出发。" : "你的提交与版本已经保留，等待真人反馈。"}</p>
          </div>
        </section>
      ) : null}
      {action.journey ? <JourneyMap journey={action.journey} /> : null}
      <article id="next-action" className={action.journey ? "current-stage-card" : "status-card"}>
        <div>
          <span className="stage-pulse" aria-hidden="true" />
          <p className="eyebrow">{action.stage}</p>
          <h2>{action.title}</h2>
        </div>
        {opensTask || opensResult ? (
          <Link
            className="button primary"
            href={opensResult ? "/app/result" : `/app/tasks/${action.resource_id}`}
          >
            {primaryActionLabel}
          </Link>
        ) : (
          <span className="waiting-mark" aria-label="等待下一步">···</span>
        )}
      </article>
      {!action.journey ? null : (
        <details className="journey-support">
          <summary>为什么是这一步</summary>
          <p>{action.reason}</p>
          <p>{action.responsible_party} · {action.feedback_expectation}</p>
        </details>
      )}
      {hasSession ? (
        <form action={logoutSession} className="quiet-exit">
          <button className="button secondary" type="submit">退出 vNext 会话</button>
        </form>
      ) : null}
    </section>
  );
}
