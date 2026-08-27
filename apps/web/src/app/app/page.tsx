import Link from "next/link";

import { logoutSession } from "@/app/actions";
import { ExperienceState, FactLegend } from "@/app/human-experience";
import {
  Assignment,
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
  const waitsForReview = action.action_type === "WAIT_FOR_REVIEW";
  const opensResult = action.action_type === "VIEW_RESULT_OR_HANDOFF";
  const assignment = opensTask || waitsForReview
    ? await learnerPageRequest<Assignment>(`/api/v1/me/assignments/${action.resource_id}`)
    : null;
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
              href: opensTask || waitsForReview ? taskHref : opensResult ? resultHref : null,
              actionLabel: opensResult ? "打开旅程结果" : null,
            }}
          />
          {assignment ? (
            <section className="current-task-card" aria-labelledby="current-task-card-title">
              <header>
                <div>
                  <p className="eyebrow">当前应做的一项 · TaskVersion v{assignment.task_version}</p>
                  <h2 id="current-task-card-title">{assignment.task_title}</h2>
                  <p>{assignment.task_purpose}</p>
                </div>
                <strong>{assignment.status}</strong>
              </header>
              <dl>
                <div><dt>任务类型</dt><dd>{assignment.journey_stage?.stage_kind ?? "正式任务"}</dd></div>
                <div><dt>预计时间</dt><dd>{assignment.estimated_duration_minutes} 分钟</dd></div>
                <div><dt>截止时间</dt><dd>未单独配置；不虚构日期</dd></div>
                <div><dt>审核边界</dt><dd>{assignment.journey_stage?.completion_policy === "LEARNER_EVIDENCE" ? "低风险学习证据；无需真人评审" : `正式任务；由 ${assignment.reviewer_display_name} 真人审核`}</dd></div>
                <div><dt>首次反馈</dt><dd>{assignment.feedback_sla_business_days} 个工作日内</dd></div>
                <div><dt>当前状态来源</dt><dd>Assignment revision {assignment.revision}</dd></div>
              </dl>
              <Link className="button primary" href={taskHref}>
                {waitsForReview ? "查看已提交版本" : opensFirstMaterial ? "打开第一份必读材料" : "打开当前任务"}
              </Link>
            </section>
          ) : null}
        </>
      ) : opensTask || waitsForReview || opensResult ? (
        <article className="status-card">
          <p className="eyebrow">{action.stage}</p>
          <h2>{action.title}</h2>
          <p>{action.reason}</p>
          {opensTask ? (
            <Link className="button primary" href={taskHref}>进入当前任务</Link>
          ) : waitsForReview ? (
            <Link className="button primary" href={taskHref}>查看已提交版本</Link>
          ) : opensResult ? (
            <Link className="button primary" href={resultHref}>查看当前结果</Link>
          ) : null}
        </article>
      ) : (
        <ExperienceState
          kind={action.action_type === "RESOLVE_ENROLLMENT" ? "locked" : "empty"}
          title={action.title}
          summary={action.reason}
          knownFacts={[
            `当前阶段：${action.stage}`,
            `责任角色：${action.responsible_party}`,
            `反馈说明：${action.feedback_expectation}`,
          ]}
          action={{ href: "/", label: "返回安全入口" }}
        />
      )}
      <JourneyProgramOverview
        currentAction={currentNode?.title ?? action.title}
        currentJourneyKey={action.journey?.stable_key}
        enrollments={enrollmentsResponse.items}
      />
      {!action.journey ? null : (
        <p className="journey-support">
          {action.responsible_party} · {action.feedback_expectation}
        </p>
      )}
      <FactLegend />
      {hasSession ? (
        <form action={logoutSession} className="quiet-exit">
          <button className="button secondary" type="submit">退出 vNext 会话</button>
        </form>
      ) : null}
    </section>
  );
}
