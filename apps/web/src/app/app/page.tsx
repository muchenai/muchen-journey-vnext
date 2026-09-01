import Link from "next/link";

import { logoutSession } from "@/app/actions";
import { ExperienceState, FactLegend } from "@/app/human-experience";
import { LiveStatusSignal } from "@/app/live-status-signal";
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
  searchParams: Promise<{ enrollment_id?: string; transition?: string }>;
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
  const currentJourneyNode = action.journey?.nodes.find((node) => node.status === "CURRENT");
  const currentNode = currentJourneyNode;
  const opensFirstMaterial = opensTask && currentNode?.position === 0;
  const beginsDayZero = opensTask && currentJourneyNode?.stage_kind === "DAY_0";
  const taskHref = `/app/tasks/${action.resource_id}${
    opensFirstMaterial ? "#first-learning-input" : ""
  }`;
  const resultHref = query.enrollment_id
    ? `/app/result?enrollment_id=${encodeURIComponent(query.enrollment_id)}`
    : "/app/result";
  const showSubmissionTransition = query.transition === "submitted";
  const primaryActionLabel = opensResult
    ? "打开旅程收获"
    : action.action_type === "REVISE_SUBMISSION"
      ? "查看反馈并修订"
      : opensFirstMaterial
        ? "打开第一份必读材料"
        : "打开当前任务";

  return (
    <section className={action.journey ? "learner-journey-page" : "content-narrow"}>
      {showSubmissionTransition ? (
        <section className="journey-transition" role="status" aria-labelledby="journey-transition-title">
          <span aria-hidden="true">✓</span>
          <div>
            <p className="eyebrow">这一站已保存</p>
            <h1 id="journey-transition-title">
              {opensResult
                ? "八个路标都已点亮"
                : opensTask
                  ? "下一站已解锁"
                  : "已经交给 Reviewer"}
            </h1>
            <p>
              {opensResult
                ? "打开旅程收获，看看你带走了什么。"
                : opensTask
                  ? "路线已经更新，继续从当前路标出发。"
                  : "你的提交与版本已经保留，等待真人反馈。"}
            </p>
          </div>
          {opensTask || opensResult ? (
            <Link
              className="button transition-action"
              href={opensResult ? resultHref : taskHref}
            >
              {opensResult ? "查看旅程收获" : "进入下一站"}
            </Link>
          ) : null}
        </section>
      ) : null}
      <LiveStatusSignal
        statusKey={`${action.action_type}:${action.resource_id ?? "none"}:${action.title}`}
        active={waitsForReview}
        title="提交成功，已交给主管评审"
        detail="无需手动刷新；页面会自动检查评分状态。"
        changedMessage="评分完成，旅程已经更新。"
        initialMessage={action.action_type === "REVISE_SUBMISSION"
          ? "评分完成，Reviewer 已返回修订建议。"
          : null}
      />
      {action.journey ? (
        <>
          <JourneyMap
            journey={action.journey}
            current={{
              position: currentNode?.position ?? 0,
              title: currentNode?.title ?? action.title,
              reason: action.reason,
              href: showSubmissionTransition ? null : opensTask || waitsForReview ? taskHref : opensResult ? resultHref : null,
              actionLabel: !showSubmissionTransition && opensResult ? primaryActionLabel : null,
            }}
          />
          {assignment && !showSubmissionTransition ? (
            <section className="current-task-card" aria-labelledby="current-task-card-title">
              <header>
                <div>
                  <p className="eyebrow">当前应做的一项 · TaskVersion v{assignment.task_version}</p>
                  <h2 id="current-task-card-title">{assignment.task_title}</h2>
                  <p>{assignment.task_purpose}</p>
                  {beginsDayZero ? <p>先带着一个真实问题出发，后面的每份材料都会给你一条线索。</p> : null}
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
                {waitsForReview ? "查看已提交版本" : primaryActionLabel}
              </Link>
            </section>
          ) : null}
        </>
      ) : query.transition === "submitted" && (opensTask || opensResult) ? null : opensTask || waitsForReview || opensResult ? (
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
        <details className="journey-support">
          <summary>为什么是这一步</summary>
          <p>{action.reason}</p>
          <p>{action.responsible_party} · {action.feedback_expectation}</p>
        </details>
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
