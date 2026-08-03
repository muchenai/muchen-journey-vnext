import Link from "next/link";

import { logoutSession } from "@/app/actions";
import { CurrentAction, hasVNextSession, learnerPageRequest } from "@/lib/server/api";
import { JourneyMap } from "./journey-map";

export const dynamic = "force-dynamic";

export default async function LearnerHome() {
  const [action, hasSession] = await Promise.all([
    learnerPageRequest<CurrentAction>("/api/v1/me/current-action"),
    hasVNextSession(),
  ]);
  const opensTask = ["START_OR_CONTINUE_TASK", "REVISE_SUBMISSION"].includes(
    action.action_type,
  );
  const opensResult = action.action_type === "VIEW_RESULT_OR_HANDOFF";

  return (
    <section className={action.journey ? "learner-journey-page" : "content-narrow"}>
      {action.journey ? <JourneyMap journey={action.journey} /> : null}
      <article className={action.journey ? "current-stage-card" : "status-card"}>
        <div>
          <span className="stage-pulse" aria-hidden="true" />
          <p className="eyebrow">{action.stage}</p>
          <h2>{action.title}</h2>
          <p>{action.reason}</p>
        </div>
        {opensTask || opensResult ? (
          <Link
            className="button primary"
            href={opensResult ? "/app/result" : `/app/tasks/${action.resource_id}`}
          >
            {opensResult ? "打开旅程结果" : "进入这一站"}
          </Link>
        ) : (
          <span className="waiting-mark" aria-label="等待下一步">···</span>
        )}
      </article>
      {!action.journey ? null : (
        <p className="journey-support">
          {action.responsible_party} · {action.feedback_expectation}
        </p>
      )}
      {hasSession ? (
        <form action={logoutSession} className="quiet-exit">
          <button className="button secondary" type="submit">退出 vNext 会话</button>
        </form>
      ) : null}
    </section>
  );
}
