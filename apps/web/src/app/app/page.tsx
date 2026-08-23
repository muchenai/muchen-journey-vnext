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
  const currentNode = action.journey?.nodes.find((node) => node.status === "CURRENT");
  const opensFirstMaterial = opensTask && currentNode?.position === 0;
  const taskHref = `/app/tasks/${action.resource_id}${
    opensFirstMaterial ? "#first-learning-input" : ""
  }`;

  return (
    <section className={action.journey ? "learner-journey-page" : "content-narrow"}>
      {action.journey ? (
        <JourneyMap
          journey={action.journey}
          current={{
            position: currentNode?.position ?? 0,
            title: currentNode?.title ?? action.title,
            reason: action.reason,
            href: opensTask ? taskHref : opensResult ? "/app/result" : null,
            actionLabel: opensResult
              ? "打开旅程结果"
              : opensFirstMaterial
                ? "打开第一份必读材料"
                : opensTask
                  ? "进入这一站"
                  : null,
          }}
        />
      ) : (
        <article className="status-card">
          <p className="eyebrow">{action.stage}</p>
          <h2>{action.title}</h2>
          <p>{action.reason}</p>
        </article>
      )}
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
