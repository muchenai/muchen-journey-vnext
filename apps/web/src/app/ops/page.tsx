import {
  assignEnrollmentReviewer,
  cancelEnrollment,
  configureNotificationEndpoint,
  redriveNotificationDelivery,
  revokeNotificationEndpoint,
} from "@/app/actions";
import {
  identityPageRequest,
  OpsAuditEntry,
  OpsEnrollment,
  OpsFormalJourney,
  OpsIdentityAccess,
  OpsInvite,
  OpsNotificationDelivery,
  OpsNotificationEndpoint,
  OpsTaskDefinition,
  RuntimeStatus,
} from "@/lib/server/api";
import { IdentityAccessPanel } from "@/app/ops/identity-access-panel";
import { InviteManagementPanel } from "@/app/ops/invite-management-panel";
import { LearnerReentryPanel } from "@/app/ops/learner-reentry-panel";
import { FormalAdmissionPanel } from "@/app/ops/formal-admission-panel";

export const dynamic = "force-dynamic";

function formatTime(value: string | null): string {
  if (!value) return "尚无心跳";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export default async function OpsPage({
  searchParams,
}: {
  searchParams: Promise<{ updated?: string }>;
}) {
  const [
    query,
    tasks,
    enrollments,
    audit,
    runtime,
    identityAccess,
    invites,
    notificationEndpoints,
    notificationDeliveries,
    formalJourneys,
  ] = await Promise.all([
    searchParams,
    identityPageRequest<{ items: OpsTaskDefinition[] }>("/api/v1/ops/task-definitions", "OPERATOR"),
    identityPageRequest<{ items: OpsEnrollment[] }>("/api/v1/ops/enrollments", "OPERATOR"),
    identityPageRequest<{ items: OpsAuditEntry[] }>("/api/v1/ops/audit?limit=20", "OPERATOR"),
    identityPageRequest<RuntimeStatus>("/api/v1/ops/runtime-status", "OPERATOR"),
    identityPageRequest<{ items: OpsIdentityAccess[] }>("/api/v1/ops/identity-access", "OPERATOR"),
    identityPageRequest<{ items: OpsInvite[] }>("/api/v1/ops/invites", "OPERATOR"),
    identityPageRequest<{ items: OpsNotificationEndpoint[] }>(
      "/api/v1/ops/notification-endpoints",
      "OPERATOR",
    ),
    identityPageRequest<{ items: OpsNotificationDelivery[] }>(
      "/api/v1/ops/notification-deliveries?status=DEAD",
      "OPERATOR",
    ),
    identityPageRequest<{ items: OpsFormalJourney[] }>(
      "/api/v1/ops/formal-journeys",
      "OPERATOR",
    ),
  ]);
  const isStaging = runtime.environment === "staging";

  return (
    <section className="ops-page">
      <p className="eyebrow">Operator · {runtime.environment}</p>
      <h1>受控运营与运行状态</h1>
      <p className="lede">
        这里没有通用状态编辑器。所有写入都绑定组织、对象、角色、expected revision、幂等键与理由。
      </p>
      <p className="notice">
        {isStaging
          ? "当前为 Alpha staging；真人身份/UAT、真实通知、物理 ACL 证据、异机恢复与发布签署未闭环前，production 仍必须 NO_GO。"
          : "当前为本地/测试环境；真人 UAT、真实通知与发布签署不在此环境中成立，发布判定必须 NO_GO。"}
      </p>
      {query.updated ? <p className="success-text" role="status">受控命令已写入并记录审计。</p> : null}

      <a className="button primary ops-primary-action" href="#learner-invites">邀请新人</a>

      <section className="panel ops-section" id="learner-invites" aria-labelledby="invite-heading">
        <p className="section-label">LEARNER INVITE / FIRST REAL LOOP</p>
        <h2 id="invite-heading">邀请新人进入当前行动</h2>
        <p>
          为一名新人选择已绑定主管和已发布任务，生成一条独立的一次性邀请链接。页面不会要求或展示内部 UUID。
        </p>
        <InviteManagementPanel
          invites={invites.items}
          identityAccess={identityAccess.items}
          tasks={tasks.items}
          journeys={formalJourneys.items}
        />
      </section>

      <section className="panel ops-section" aria-labelledby="runtime-heading">
        <div className="section-heading-row">
          <div>
            <p className="section-label">REVISION / HEALTH / WORKER / OBSERVABILITY</p>
            <h2 id="runtime-heading">运行快照</h2>
          </div>
          <span className={`material-status ${runtime.worker.stale ? "incomplete" : "complete"}`}>
            Worker {runtime.worker.status}
          </span>
        </div>
        <dl className="ops-facts">
          <div><dt>Release</dt><dd>{runtime.release}</dd></div>
          <div><dt>Migration</dt><dd>{runtime.migration_revision}</dd></div>
          <div><dt>Config schema</dt><dd>V{runtime.config_schema_version}</dd></div>
          <div><dt>API / DB</dt><dd>{runtime.api.status} / {runtime.database.status}</dd></div>
          <div><dt>Worker revision</dt><dd>{runtime.worker.release ?? "未知"}</dd></div>
          <div><dt>Worker heartbeat</dt><dd>{formatTime(runtime.worker.last_seen_at)}</dd></div>
          <div><dt>Outbox / retry / dead</dt><dd>{runtime.metrics.outbox_backlog} / {runtime.metrics.notification_retry_wait} / {runtime.metrics.notification_dead}</dd></div>
          <div><dt>Oldest pending</dt><dd>{runtime.metrics.oldest_pending_seconds}s</dd></div>
          <div><dt>Observability</dt><dd>{runtime.observability_mode} · external=false</dd></div>
        </dl>
      </section>

      <section className="panel ops-section" aria-labelledby="task-heading">
        <p className="section-label">VERSIONED TASK / CONFIG</p>
        <h2 id="task-heading">不可变 TaskVersion 清单</h2>
        <p>配置合同固定为 V{runtime.config_schema_version}；任务发布仍使用现有 create/publish 意图命令，Assignment 永远固定原版本。</p>
        <ul className="ops-list">
          {tasks.items.map((task) => (
            <li key={task.id}>
              <div><strong>{task.stable_key}</strong><span>{task.status} · definition revision {task.revision}</span></div>
              <span>{task.versions.map((version) => `V${version.version} ${version.title}`).join(" · ") || "尚未发布"}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ops-section" id="admission-decisions" aria-labelledby="enrollment-heading">
        <p className="section-label">ENROLLMENT COMMANDS</p>
        <h2 id="enrollment-heading">Enrollment 受控处置</h2>
        <ul className="ops-list">
          {enrollments.items.map((enrollment) => (
            <li key={enrollment.id} className="ops-enrollment">
              <div className="ops-enrollment-heading">
                <div>
                  <strong>{enrollment.learner_display_name}</strong>
                  <span>{enrollment.status} · revision {enrollment.revision} · {enrollment.assignment_statuses.join(" / ") || "无任务"}</span>
                </div>
                <span className="badge">主管：{enrollment.reviewer_display_name}</span>
              </div>
              {enrollment.open_review_status ? (
                <p className="inline-error">已有 {enrollment.open_review_status} Review；Reviewer 重分配与 Enrollment 取消均被状态机阻断。</p>
              ) : null}
              {enrollment.admission_decision ? (
                <div className="admission-preview">
                  <strong>{enrollment.admission_total_score} / 100 · {enrollment.admission_tier} 档</strong>
                  <span>人工结论：{enrollment.admission_decision} · 已不可变记录</span>
                </div>
              ) : null}
              {enrollment.allowed_commands.includes("create_formal_admission") ? (
                <FormalAdmissionPanel enrollmentId={enrollment.id} />
              ) : null}
              {enrollment.allowed_commands.includes("create_learner_reentry") ? (
                <LearnerReentryPanel
                  enrollmentId={enrollment.id}
                  enrollmentRevision={enrollment.revision}
                />
              ) : null}
              {enrollment.allowed_commands.includes("assign_reviewer") ? (
                <form action={assignEnrollmentReviewer} className="ops-command-form">
                  <input type="hidden" name="enrollment_id" value={enrollment.id} />
                  <input type="hidden" name="revision" value={enrollment.revision} />
                  <label>
                    新 Reviewer UUID
                    <input name="reviewer_id" required pattern="[0-9a-fA-F-]{36}" autoComplete="off" />
                  </label>
                  <label>
                    分配理由
                    <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                  </label>
                  <button className="button secondary compact" type="submit">受控分配 Reviewer</button>
                </form>
              ) : null}
              {enrollment.allowed_commands.includes("cancel_enrollment") ? (
                <form action={cancelEnrollment} className="ops-command-form">
                  <input type="hidden" name="enrollment_id" value={enrollment.id} />
                  <input type="hidden" name="revision" value={enrollment.revision} />
                  <label>
                    取消理由
                    <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                  </label>
                  <button className="button secondary compact" type="submit">受控取消 Enrollment</button>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ops-section" aria-labelledby="notification-heading">
        <p className="section-label">RECIPIENT / DELIVERY / REDRIVE</p>
        <h2 id="notification-heading">飞书通知受控处置</h2>
        <p>
          open_id 仅在提交时进入服务端加密流程，页面不会回显。真实发送仍由 Worker 配置门禁控制；DEAD 只能保留历史后人工重驱。
        </p>
        <ul className="ops-list">
          {enrollments.items.map((enrollment) => {
            const endpoint = notificationEndpoints.items.find(
              (item) => item.user_id === enrollment.learner_id,
            );
            return (
              <li key={`notification-${enrollment.id}`} className="ops-enrollment">
                <div className="ops-enrollment-heading">
                  <div>
                    <strong>{enrollment.learner_display_name}</strong>
                    <span>
                      {endpoint
                        ? `${endpoint.status} · revision ${endpoint.revision} · updated ${formatTime(endpoint.updated_at)}`
                        : "尚无飞书通知接收人"}
                    </span>
                  </div>
                  <span className="badge">FEISHU / open_id</span>
                </div>
                <form action={configureNotificationEndpoint} className="ops-command-form">
                  <input type="hidden" name="user_id" value={enrollment.learner_id} />
                  <input type="hidden" name="revision" value={endpoint?.revision ?? 0} />
                  <label>
                    新 open_id（提交后不回显）
                    <input
                      type="password"
                      name="receive_id"
                      required
                      pattern="ou_[A-Za-z0-9_-]{8,120}"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    配置理由
                    <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                  </label>
                  <button className="button secondary compact" type="submit">
                    {endpoint ? "替换并启用接收人" : "配置接收人"}
                  </button>
                </form>
                {endpoint?.status === "ACTIVE" ? (
                  <form action={revokeNotificationEndpoint} className="ops-command-form">
                    <input type="hidden" name="endpoint_id" value={endpoint.id} />
                    <input type="hidden" name="revision" value={endpoint.revision} />
                    <label>
                      撤销理由
                      <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                    </label>
                    <button className="button secondary compact" type="submit">撤销接收人</button>
                  </form>
                ) : null}
              </li>
            );
          })}
        </ul>
        <h3>DEAD 投递</h3>
        {notificationDeliveries.items.length === 0 ? <p>当前没有 DEAD 通知。</p> : null}
        <ul className="ops-list">
          {notificationDeliveries.items.map((delivery) => (
            <li key={delivery.id} className="ops-enrollment">
              <div>
                <strong>{delivery.channel} · {delivery.status}</strong>
                <span>
                  attempts {delivery.attempt_count} · redrives {delivery.redrive_count} · {delivery.last_error_code ?? "无错误码"}
                </span>
              </div>
              <form action={redriveNotificationDelivery} className="ops-command-form">
                <input type="hidden" name="delivery_id" value={delivery.id} />
                <input type="hidden" name="revision" value={delivery.revision} />
                <label>
                  重驱理由
                  <input name="reason" required minLength={10} maxLength={500} autoComplete="off" />
                </label>
                <button className="button secondary compact" type="submit">受控人工重驱</button>
              </form>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ops-section" aria-labelledby="identity-heading">
        <p className="section-label">REAL IDENTITY / MINIMUM ACCESS</p>
        <h2 id="identity-heading">飞书身份访问</h2>
        <p>
          仅管理 Reviewer 与 Operator 的真实身份入口。绑定链接仅显示一次；撤销身份会立即使其现有会话失效。
        </p>
        <IdentityAccessPanel items={identityAccess.items} />
      </section>

      <section className="panel ops-section" aria-labelledby="audit-heading">
        <p className="section-label">SAFE AUDIT VIEW</p>
        <h2 id="audit-heading">最近审计元数据</h2>
        <p>API 最多查询 31 天/100 行；仅安全 allowlist 字段出现在这里，其余字段只显示已裁剪键名。</p>
        <div className="audit-table-wrap">
          <table>
            <thead><tr><th>时间</th><th>动作</th><th>对象</th><th>结果</th><th>安全字段 / 裁剪</th></tr></thead>
            <tbody>
              {audit.items.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTime(entry.occurred_at)}</td>
                  <td>{entry.action}</td>
                  <td>{entry.resource_type}</td>
                  <td>{entry.result}</td>
                  <td><code>{JSON.stringify(entry.safe_details)}</code><small>裁剪：{entry.redacted_fields.join(", ") || "无"}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
