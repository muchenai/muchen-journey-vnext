"use client";

import { useActionState, useState } from "react";

import {
  createLearnerInvite,
  InviteActionState,
  publishFormalJourney,
  PublishFormalJourneyActionState,
  revokeLearnerInvite,
  updateInvitationControl,
} from "@/app/actions";
import {
  OpsFormalJourney,
  OpsIdentityAccess,
  OpsInvite,
  OpsInvitationControl,
  OpsTaskDefinition,
} from "@/lib/server/api";

const INITIAL_STATE: InviteActionState = {};
const INITIAL_PUBLISH_STATE: PublishFormalJourneyActionState = {};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

const STATUS_LABELS: Record<OpsInvite["status"], string> = {
  ACTIVE: "待使用",
  CONSUMED: "已使用",
  EXPIRED: "已过期",
  REVOKED: "已撤销",
};

function formatJourneyOptionLabel(journey: OpsFormalJourney): string {
  const title = journey.title.trim();
  const versionLabel = `V${journey.version}`;
  const titleAlreadyIncludesVersion = new RegExp(
    `(?:^|[·｜\\s])${versionLabel}$`,
    "i",
  ).test(title);

  return `${title}${titleAlreadyIncludesVersion ? "" : ` · ${versionLabel}`} · ${journey.stages.length} 站`;
}

function CreateInviteForm({
  reviewers,
  tasks,
  journeys,
  invitationsEnabled,
}: {
  reviewers: OpsIdentityAccess[];
  tasks: OpsTaskDefinition[];
  journeys: OpsFormalJourney[];
  invitationsEnabled: boolean;
}) {
  const [state, action, pending] = useActionState(createLearnerInvite, INITIAL_STATE);
  const [copied, setCopied] = useState(false);
  const taskVersions = tasks
    .filter((task) => task.status === "PUBLISHED")
    .flatMap((task) => task.versions.map((version) => ({ ...version, stableKey: task.stable_key })));

  async function copyLink() {
    if (!state.joinPath) return;
    await navigator.clipboard.writeText(new URL(state.joinPath, window.location.origin).href);
    setCopied(true);
  }

  if (state.joinPath) {
    return (
      <div className="identity-link-result" role="status">
        <strong>新人邀请链接已生成</strong>
        <p>
          24 小时内使用，有效至 {formatTime(state.expiresAt ?? new Date().toISOString())}。
          原始链接仅在本次页面状态显示；复制后交给一名预定 Learner。
        </p>
        <code>{state.joinPath}</code>
        <button className="button primary compact" type="button" onClick={copyLink}>
          {copied ? "已复制完整链接" : "复制完整邀请链接"}
        </button>
        <p className="status-meta">需要邀请下一人时刷新运营页，再生成一条独立链接。</p>
      </div>
    );
  }

  if (!invitationsEnabled) {
    return (
      <p className="inline-error" role="status">
        新邀请已冻结；既有 Enrollment、提交、评审和重新进入路径继续保留。
      </p>
    );
  }

  if (reviewers.length === 0 || (journeys.length === 0 && taskVersions.length === 0)) {
    return (
      <p className="inline-error" role="alert">
        {reviewers.length === 0
          ? "当前没有已绑定飞书身份的 Reviewer；请先在本页“飞书身份访问”完成绑定。"
          : "当前没有已发布的正式旅程或兼容任务版本；不能创建邀请。"}
      </p>
    );
  }

  return (
    <form action={action} className="ops-command-form invite-create-form">
      <label>
        分配主管
        <select name="reviewer_id" required defaultValue="">
          <option value="" disabled>选择已绑定 Reviewer</option>
          {reviewers.map((reviewer) => (
            <option key={reviewer.user_id} value={reviewer.user_id}>
              {reviewer.display_name}
            </option>
          ))}
        </select>
      </label>
      {journeys.length > 0 ? (
        <label>
          固定旅程
          <select name="journey_version_id" required defaultValue={journeys[0].id}>
            {journeys.map((journey) => (
              <option key={journey.id} value={journey.id}>
                {formatJourneyOptionLabel(journey)}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label>
          兼容任务（仅旧 Alpha）
          <select name="task_version_id" required defaultValue="">
            <option value="" disabled>选择已发布任务版本</option>
            {taskVersions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.stableKey} · V{version.version} · {version.title}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="invite-purpose-field">
        邀请用途
        <input
          name="purpose"
          required
          minLength={3}
          maxLength={200}
          defaultValue={
            journeys.length > 0
              ? "加入 Muchen Journey 受控内测并完成正式探索营"
              : "安全重新进入旧 Alpha 单任务兼容路径"
          }
          autoComplete="off"
        />
      </label>
      <button className="button primary" type="submit" disabled={pending}>
        {pending ? "正在生成…" : "生成 24 小时邀请链接"}
      </button>
      {state.error ? (
        <p className="inline-error" role="alert">
          {state.error}
          {state.requestId ? <code>request ID: {state.requestId}</code> : null}
        </p>
      ) : null}
    </form>
  );
}

function PublishFormalJourneyForm({
  reviewers,
  expectedCurrentVersion,
}: {
  reviewers: OpsIdentityAccess[];
  expectedCurrentVersion: number;
}) {
  const [state, action, pending] = useActionState(
    publishFormalJourney,
    INITIAL_PUBLISH_STATE,
  );

  return (
    <form action={action} className="ops-command-form invite-create-form">
      <div>
        <strong>发布正式探索营 V2</strong>
        <p className="status-meta">
          V2 包含完整一天学习输入、四个宝藏、三项真实评测及人工准入评分。V1 与现有 Enrollment 不迁移。
        </p>
      </div>
      <input type="hidden" name="expected_current_version" value={expectedCurrentVersion} />
      <label>
        已完成线下复核的 Reviewer
        <select name="reviewed_by" required defaultValue="">
          <option value="" disabled>选择独立 Reviewer</option>
          {reviewers.map((reviewer) => (
            <option key={reviewer.user_id} value={reviewer.user_id}>
              {reviewer.display_name}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox-row">
        <input name="review_acknowledged" type="checkbox" required />
        我确认该 Reviewer 已逐项复核 V2 学习内容、题面、Rubric 与准入边界；发布后正文不可原地修改
      </label>
      <button className="button secondary" type="submit" disabled={pending}>
        {pending ? "正在发布…" : "发布正式探索营 V2"}
      </button>
      {state.error ? (
        <p className="inline-error" role="alert">
          {state.error}
          {state.requestId ? <code>request ID: {state.requestId}</code> : null}
        </p>
      ) : null}
    </form>
  );
}

export function InviteManagementPanel({
  invites,
  invitationControl,
  identityAccess,
  tasks,
  journeys,
}: {
  invites: OpsInvite[];
  invitationControl: OpsInvitationControl;
  identityAccess: OpsIdentityAccess[];
  tasks: OpsTaskDefinition[];
  journeys: OpsFormalJourney[];
}) {
  const reviewers = identityAccess.filter(
    (item) => item.role === "REVIEWER" && item.identity_status === "LINKED",
  );
  const latestJourney = journeys[0];
  const v2Published = latestJourney?.stages.some(
    (stage) => stage.stable_key === "ASM-003-DATA-CONSTRUCTION",
  ) ?? false;

  return (
    <>
      <section className="admission-form" aria-labelledby="invite-control-title">
        <div className="ops-enrollment-heading">
          <div>
            <h3 id="invite-control-title">新邀请总开关</h3>
            <span>当前：{invitationControl.state === "OPEN" ? "开放" : "已冻结"} · revision {invitationControl.revision}</span>
          </div>
          <span className={`material-status ${invitationControl.new_invites_enabled ? "complete" : "incomplete"}`}>
            {invitationControl.new_invites_enabled ? "OPEN" : "FROZEN"}
          </span>
        </div>
        <p>停止条件出现时只冻结新邀请，不撤销已接受邀请，也不删除任何业务事实。</p>
        <form action={updateInvitationControl} className="ops-command-form">
          <input type="hidden" name="revision" value={invitationControl.revision} />
          <input
            type="hidden"
            name="target_state"
            value={invitationControl.new_invites_enabled ? "FROZEN" : "OPEN"}
          />
          <label>
            {invitationControl.new_invites_enabled ? "冻结理由" : "恢复理由"}
            <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
          </label>
          <button className="button secondary compact" type="submit">
            {invitationControl.new_invites_enabled ? "停止创建新邀请" : "恢复创建新邀请"}
          </button>
        </form>
      </section>
      {!v2Published && reviewers.length > 0 ? (
        <PublishFormalJourneyForm
          reviewers={reviewers}
          expectedCurrentVersion={latestJourney?.version ?? 0}
        />
      ) : null}
      <CreateInviteForm
        reviewers={reviewers}
        tasks={tasks}
        journeys={journeys}
        invitationsEnabled={invitationControl.new_invites_enabled}
      />
      <h3>最近邀请</h3>
      {invites.length === 0 ? <p>尚未创建新人邀请。</p> : null}
      <ul className="ops-list invite-list">
        {invites.map((invite) => (
          <li key={invite.id}>
            <div className="ops-enrollment-heading">
              <div>
                <strong>{invite.purpose}</strong>
                <span>到期 {formatTime(invite.expires_at)} · revision {invite.revision}</span>
              </div>
              <span className={`material-status ${invite.status === "ACTIVE" ? "complete" : "incomplete"}`}>
                {STATUS_LABELS[invite.status]}
              </span>
            </div>
            {invite.status === "ACTIVE" ? (
              <form action={revokeLearnerInvite} className="ops-command-form">
                <input type="hidden" name="invite_id" value={invite.id} />
                <input type="hidden" name="revision" value={invite.revision} />
                <label>
                  撤销理由
                  <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                </label>
                <button className="button secondary compact" type="submit">撤销邀请</button>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
