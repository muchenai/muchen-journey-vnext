"use client";

import { useActionState, useState } from "react";

import {
  createIdentityLink,
  IdentityLinkActionState,
  revokeExternalIdentity,
  revokeIdentityLink,
} from "@/app/actions";
import { OpsIdentityAccess } from "@/lib/server/api";

const INITIAL_STATE: IdentityLinkActionState = {};

function formatTime(value: string | null): string {
  if (!value) return "无";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function CreateLinkForm({ item }: { item: OpsIdentityAccess }) {
  const [state, action, pending] = useActionState(createIdentityLink, INITIAL_STATE);
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    if (!state.startPath) return;
    await navigator.clipboard.writeText(new URL(state.startPath, window.location.origin).href);
    setCopied(true);
  }

  if (state.startPath) {
    return (
      <div className="identity-link-result" role="status">
        <strong>一次性绑定链接已生成</strong>
        <p>
          仅发给 {item.display_name}；有效至 {formatTime(state.expiresAt ?? null)}。
          页面刷新后不再显示原始链接。
        </p>
        <code>{state.startPath}</code>
        <button className="button secondary compact" type="button" onClick={copyLink}>
          {copied ? "已复制" : "复制完整链接"}
        </button>
      </div>
    );
  }

  return (
    <form action={action} className="ops-command-form identity-create-form">
      <input type="hidden" name="target_user_id" value={item.user_id} />
      <input type="hidden" name="role" value={item.role} />
      <p>30 分钟有效，原始链接只显示一次。</p>
      <button className="button secondary compact" type="submit" disabled={pending}>
        {pending ? "正在生成…" : "生成绑定链接"}
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

function IdentityAccessItem({ item }: { item: OpsIdentityAccess }) {
  const roleName = item.role === "OPERATOR"
    ? "Operator"
    : item.role === "CONTENT_EDITOR"
      ? "Content Editor"
      : "Reviewer";
  return (
    <li>
      <div className="ops-enrollment-heading">
        <div>
          <strong>{item.display_name}</strong>
          <span>{roleName} · {item.user_id}</span>
        </div>
        <span className={`material-status ${item.identity_status === "LINKED" ? "complete" : "incomplete"}`}>
          {item.identity_status}
        </span>
      </div>
      {item.identity_status === "LINKED" ? (
        <p>已绑定飞书 · 验证时间 {formatTime(item.identity_verified_at)}</p>
      ) : item.link_status ? (
        <p>最近绑定链接：{item.link_status} · 到期 {formatTime(item.link_expires_at)}</p>
      ) : (
        <p>尚未绑定真实飞书身份。</p>
      )}

      {item.allowed_commands.includes("create_identity_link") ? <CreateLinkForm item={item} /> : null}

      {item.allowed_commands.includes("revoke_identity_link") && item.link_id && item.link_revision ? (
        <form action={revokeIdentityLink} className="ops-command-form">
          <input type="hidden" name="link_id" value={item.link_id} />
          <input type="hidden" name="revision" value={item.link_revision} />
          <label>
            撤销理由
            <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
          </label>
          <button className="button secondary compact" type="submit">撤销待绑定链接</button>
        </form>
      ) : null}

      {item.allowed_commands.includes("revoke_external_identity") && item.identity_id && item.identity_revision ? (
        <form action={revokeExternalIdentity} className="ops-command-form">
          <input type="hidden" name="identity_id" value={item.identity_id} />
          <input type="hidden" name="revision" value={item.identity_revision} />
          <label>
            撤销理由
            <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
          </label>
          <button className="button secondary compact" type="submit">撤销飞书身份</button>
        </form>
      ) : null}

      {item.is_current_actor && item.identity_status === "LINKED" ? (
        <p className="status-meta">当前登录身份不能自我撤销，避免意外锁死运营入口。</p>
      ) : null}
    </li>
  );
}

export function IdentityAccessPanel({ items }: { items: OpsIdentityAccess[] }) {
  return (
    <ul className="ops-list identity-access-list">
      {items.map((item) => (
        <IdentityAccessItem item={item} key={`${item.user_id}:${item.role}`} />
      ))}
    </ul>
  );
}
