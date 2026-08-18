"use client";

import { useActionState, useState } from "react";

import {
  createLearnerReentry,
  LearnerReentryActionState,
} from "@/app/actions";

const INITIAL_STATE: LearnerReentryActionState = {};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

export function LearnerReentryPanel({
  enrollmentId,
  enrollmentRevision,
}: {
  enrollmentId: string;
  enrollmentRevision: number;
}) {
  const [state, action, pending] = useActionState(createLearnerReentry, INITIAL_STATE);
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    if (!state.joinPath) return;
    await navigator.clipboard.writeText(new URL(state.joinPath, window.location.origin).href);
    setCopied(true);
  }

  if (state.joinPath) {
    return (
      <div className="identity-link-result" role="status">
        <strong>一次性重新进入链接已生成</strong>
        <p>
          30 分钟内使用，有效至 {formatTime(state.expiresAt ?? new Date().toISOString())}。
          链接只恢复原 Learner 会话，不创建新的业务事实。
        </p>
        <button className="button primary compact" type="button" onClick={copyLink}>
          {copied ? "已复制完整链接" : "复制完整重新进入链接"}
        </button>
        <p className="status-meta">原始凭据仅保留在本次页面状态；使用后立即失效并轮换旧会话。</p>
      </div>
    );
  }

  return (
    <form action={action} className="ops-command-form">
      <input type="hidden" name="enrollment_id" value={enrollmentId} />
      <input type="hidden" name="revision" value={enrollmentRevision} />
      <label>
        重新进入理由
        <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
      </label>
      <button className="button secondary compact" type="submit" disabled={pending}>
        {pending ? "正在生成…" : "生成 30 分钟重新进入链接"}
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
