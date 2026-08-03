"use client";

import { useActionState, useState } from "react";

import {
  createLearnerInvite,
  InviteActionState,
  revokeLearnerInvite,
} from "@/app/actions";
import { OpsIdentityAccess, OpsInvite, OpsJourneyDefinition } from "@/lib/server/api";

const INITIAL_STATE: InviteActionState = {};

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

function CreateInviteForm({
  reviewers,
  journeys,
}: {
  reviewers: OpsIdentityAccess[];
  journeys: OpsJourneyDefinition[];
}) {
  const [state, action, pending] = useActionState(createLearnerInvite, INITIAL_STATE);
  const [copied, setCopied] = useState(false);
  const journeyVersions = journeys
    .filter((journey) => journey.status === "PUBLISHED" && journey.kind === "ALPHA_VALIDATION")
    .flatMap((journey) =>
      journey.versions.map((version) => ({ ...version, stableKey: journey.stable_key })),
    );

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

  if (reviewers.length === 0 || journeyVersions.length === 0) {
    return (
      <p className="inline-error" role="alert">
        {reviewers.length === 0
          ? "当前没有已绑定飞书身份的 Reviewer；请先在本页“飞书身份访问”完成绑定。"
          : "当前没有可激活的 Alpha 旅程版本；不能创建无法进入真实闭环的邀请。"}
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
      <label>
        固定旅程版本
        <select name="journey_version_id" required defaultValue="">
          <option value="" disabled>选择已发布 Alpha 旅程</option>
          {journeyVersions.map((version) => (
            <option key={version.id} value={version.id}>
              {version.stableKey} · V{version.version} · {version.title} · {version.stages.length} 阶段
            </option>
          ))}
        </select>
      </label>
      <label className="invite-purpose-field">
        邀请用途
        <input
          name="purpose"
          required
          minLength={3}
          maxLength={200}
          defaultValue="加入 Muchen Journey Alpha 试点并完成首个真实任务"
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

export function InviteManagementPanel({
  invites,
  identityAccess,
  journeys,
}: {
  invites: OpsInvite[];
  identityAccess: OpsIdentityAccess[];
  journeys: OpsJourneyDefinition[];
}) {
  const reviewers = identityAccess.filter(
    (item) => item.role === "REVIEWER" && item.identity_status === "LINKED",
  );

  return (
    <>
      <CreateInviteForm reviewers={reviewers} journeys={journeys} />
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
