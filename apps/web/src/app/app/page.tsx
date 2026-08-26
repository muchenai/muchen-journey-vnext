import Link from "next/link";

import { logoutSession } from "@/app/actions";
import {
  CurrentAction,
  hasVNextSession,
  LearnerEnrollment,
  learnerPageRequest,
} from "@/lib/server/api";
import { JourneyMap } from "./journey-map";
import { JourneyProgramOverview } from "./program-overview";

export const dynamic = "force-dynamic";

export default async function LearnerHome({
  searchParams,
}: {
  searchParams: Promise<{ enrollment_id?: string }>;
}) {
  const query = await searchParams;
  const enrollmentQuery = query.enrollment_id
    ? `?enrollment_id=${encodeURIComponent(query.enrollment_id)}`
    : "";
  const [action, enrollmentsResponse, hasSession] = await Promise.all([
    learnerPageRequest<CurrentAction>(`/api/v1/me/current-action${enrollmentQuery}`),
    learnerPageRequest<{ items: LearnerEnrollment[] }>("/api/v1/me/enrollments"),
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
  const resultHref = query.enrollment_id
    ? `/app/result?enrollment_id=${encodeURIComponent(query.enrollment_id)}`
    : "/app/result";

  return (
    <section className={action.journey ? "learner-journey-page" : "content-narrow"}>
      {action.journey ? (
        <>
          <JourneyMap
            journey={action.journey}
            current={{
              position: currentNode?.position ?? 0,
              title: currentNode?.title ?? action.title,
              reason: action.reason,
              href: opensTask ? taskHref : opensResult ? resultHref : null,
              actionLabel: opensResult
                ? "打开旅程结果"
                : opensFirstMaterial
                  ? "打开第一份必读材料"
                  : opensTask
                    ? "进入这一站"
                    : null,
            }}
          />
        </>
      ) : (
        <article className="status-card">
          <p className="eyebrow">{action.stage}</p>
          <h2>{action.title}</h2>
          <p>{action.reason}</p>
          {!action.journey && opensTask ? (
            <Link className="button primary" href={taskHref}>进入当前任务</Link>
          ) : !action.journey && opensResult ? (
            <Link className="button primary" href={resultHref}>查看当前结果</Link>
          ) : null}
        </article>
      )}
      <JourneyProgramOverview
        currentAction={currentNode?.title ?? action.title}
        enrollments={enrollmentsResponse.items}
      />
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
