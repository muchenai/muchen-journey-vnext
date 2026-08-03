"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  anonymousApiRequest,
  ApiRequestError,
  apiRequest,
  cookieValue,
  CSRF_COOKIE,
  JOIN_COOKIE,
  SESSION_COOKIE,
} from "@/lib/server/api";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function requiredUuid(data: FormData, key: string): string {
  const value = data.get(key);
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new Error("资源标识无效。请刷新页面后重试。");
  }
  return value;
}

function requiredRevision(data: FormData): number {
  const value = Number(data.get("revision"));
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error("版本信息无效。请刷新页面后重试。");
  }
  return value;
}

function commandHeaders(): HeadersInit {
  return { "Idempotency-Key": randomUUID() };
}

function requiredIdempotencyKey(data: FormData, key: string): string {
  const value = data.get(key);
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new Error("重试标识无效。请刷新页面后重试。");
  }
  return value;
}

function attachmentIds(data: FormData): string[] {
  const values = data.getAll("attachment_ids");
  if (values.length > 5 || values.some((value) => typeof value !== "string" || !UUID_PATTERN.test(value))) {
    throw new Error("附件选择无效。请刷新页面后重试。");
  }
  return values as string[];
}

export type SubmissionActionState = {
  error?: string;
  requestId?: string;
};

function submissionError(error: unknown): SubmissionActionState {
  if (error instanceof ApiRequestError) {
    return { error: error.message, requestId: error.requestId };
  }
  return { error: error instanceof Error ? error.message : "操作没有完成，请重试。" };
}

const JOIN_SUMMARY_COOKIE = "journey_next_join_summary";

function cookieSecure(): boolean {
  return ["staging", "production"].includes(process.env.APP_ENV ?? "local");
}

function safeJoinError(error: unknown): never {
  if (error instanceof ApiRequestError) {
    const query = new URLSearchParams({ code: error.code, request_id: error.requestId });
    redirect(`/join?${query.toString()}`);
  }
  throw error;
}

export async function exchangeInvite(data: FormData) {
  const token = data.get("token");
  if (typeof token !== "string" || token.length < 32 || token.length > 256) {
    redirect("/join?code=INVITE_EXPIRED_OR_REVOKED");
  }
  let exchange: {
    data: {
      flow: "JOIN" | "REENTRY";
      purpose: string;
      expires_at: string;
      csrf_token: string;
    };
    setCookies: string[];
  };
  try {
    exchange = await anonymousApiRequest("/api/v1/join/exchange", {
      method: "POST",
      body: JSON.stringify({ token, return_to: "/app" }),
    });
  } catch (error) {
    safeJoinError(error);
  }
  const joinToken = cookieValue(exchange.setCookies, JOIN_COOKIE);
  if (!joinToken) throw new Error("API 未返回安全加入上下文。");
  const cookieStore = await cookies();
  const maxAge = Math.max(
    1,
    Math.floor((new Date(exchange.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const options = { path: "/", sameSite: "lax" as const, secure: cookieSecure(), maxAge };
  cookieStore.set(JOIN_COOKIE, joinToken, { ...options, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, exchange.data.csrf_token, { ...options, httpOnly: false });
  cookieStore.set(
    JOIN_SUMMARY_COOKIE,
    Buffer.from(
      JSON.stringify({
        flow: exchange.data.flow,
        purpose: exchange.data.purpose,
        expires_at: exchange.data.expires_at,
      }),
    ).toString("base64url"),
    { ...options, httpOnly: true },
  );
  redirect("/join");
}

export async function confirmIdentity(data: FormData) {
  const displayName = data.get("display_name");
  const acceptedPurpose = data.get("accepted_purpose") === "yes";
  if (
    displayName !== null
    && (typeof displayName !== "string" || !displayName.trim() || displayName.length > 120)
  ) {
    redirect("/join?code=VALIDATION_FAILED");
  }
  if (!acceptedPurpose) redirect("/join?code=PURPOSE_NOT_ACCEPTED");
  const cookieStore = await cookies();
  const joinToken = cookieStore.get(JOIN_COOKIE)?.value;
  const csrfToken = cookieStore.get(CSRF_COOKIE)?.value;
  if (!joinToken || !csrfToken) redirect("/join?code=INVITE_EXPIRED_OR_REVOKED");
  let confirmation: {
    data: { expires_at: string; csrf_token: string };
    setCookies: string[];
  };
  try {
    confirmation = await anonymousApiRequest("/api/v1/identity/confirm", {
      method: "POST",
      headers: {
        Cookie: `${JOIN_COOKIE}=${joinToken}; ${CSRF_COOKIE}=${csrfToken}`,
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({
        display_name: typeof displayName === "string" ? displayName.trim() : null,
        accepted_purpose: true,
        return_to: "/app",
      }),
    });
  } catch (error) {
    safeJoinError(error);
  }
  const sessionToken = cookieValue(confirmation.setCookies, SESSION_COOKIE);
  if (!sessionToken) throw new Error("API 未返回安全 vNext 会话。");
  const maxAge = Math.max(
    1,
    Math.floor((new Date(confirmation.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const options = { path: "/", sameSite: "lax" as const, secure: cookieSecure(), maxAge };
  cookieStore.set(SESSION_COOKIE, sessionToken, { ...options, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, confirmation.data.csrf_token, { ...options, httpOnly: false });
  cookieStore.delete(JOIN_COOKIE);
  cookieStore.delete(JOIN_SUMMARY_COOKIE);
  revalidatePath("/app");
  redirect("/app");
}

export async function logoutSession() {
  await apiRequest("/api/v1/session/logout", "LEARNER", { method: "POST" });
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE);
  cookieStore.delete(CSRF_COOKIE);
  redirect("/");
}

export async function startAssignment(data: FormData) {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/me/assignments/${assignmentId}/start`, "LEARNER", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
  revalidatePath("/app");
  redirect(`/app/tasks/${assignmentId}`);
}

export async function submitAssignment(
  _previousState: SubmissionActionState,
  data: FormData,
): Promise<SubmissionActionState> {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  const idempotencyKey = requiredIdempotencyKey(data, "submission_idempotency_key");
  const body = data.get("body");
  if (typeof body !== "string" || body.trim().length < 40 || body.length > 8_000) {
    return { error: "提交内容需为 40–8000 个字符。草稿仍保留在当前页面。" };
  }
  try {
    await apiRequest(`/api/v1/me/assignments/${assignmentId}/submissions`, "LEARNER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        body: body.trim(),
        attachment_ids: attachmentIds(data),
      }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath("/app");
  redirect("/app");
}

export async function saveSubmissionDraft(
  _previousState: SubmissionActionState,
  data: FormData,
): Promise<SubmissionActionState> {
  const assignmentId = requiredUuid(data, "assignment_id");
  const expectedRevision = requiredRevision(data);
  const idempotencyKey = requiredIdempotencyKey(data, "draft_idempotency_key");
  const body = data.get("body");
  if (typeof body !== "string" || body.length > 8_000) {
    return { error: "草稿内容不能超过 8000 个字符。" };
  }
  try {
    await apiRequest(`/api/v1/me/assignments/${assignmentId}/draft`, "LEARNER", {
      method: "PUT",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        body,
        attachment_ids: attachmentIds(data),
      }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath(`/app/tasks/${assignmentId}`);
  redirect(`/app/tasks/${assignmentId}?draft=saved`);
}

const ALLOWED_ATTACHMENT_TYPES = new Set([
  "text/plain",
  "application/pdf",
  "image/png",
  "image/jpeg",
]);

export type AttachmentUploadIntent = {
  id: string;
  upload_url: string;
  upload_headers: Record<string, string>;
  upload_expires_at: string;
};

type AttachmentUploadInput = {
  assignmentId: string;
  originalFilename: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
};

export async function createSubmissionAttachmentUpload(
  input: AttachmentUploadInput,
): Promise<SubmissionActionState & { intent?: AttachmentUploadIntent }> {
  try {
    if (!UUID_PATTERN.test(input.assignmentId)) {
      return { error: "任务标识无效，请刷新页面后重试。" };
    }
    if (!Number.isSafeInteger(input.sizeBytes) || input.sizeBytes < 1) {
      return { error: "请选择一个非空附件。" };
    }
    if (input.sizeBytes > 5 * 1024 * 1024) {
      return { error: "附件不能超过 5 MiB。" };
    }
    if (!ALLOWED_ATTACHMENT_TYPES.has(input.contentType)) {
      return { error: "附件只支持 TXT、PDF、PNG 或 JPEG。" };
    }
    if (!/^[0-9a-f]{64}$/.test(input.sha256)) {
      return { error: "附件完整性摘要无效。" };
    }
    const intent = await apiRequest<AttachmentUploadIntent>(
      "/api/v1/attachments/presign",
      "LEARNER",
      {
        method: "POST",
        headers: commandHeaders(),
        body: JSON.stringify({
          assignment_id: input.assignmentId,
          purpose: "SUBMISSION_EVIDENCE",
          original_filename: input.originalFilename,
          content_type: input.contentType,
          size_bytes: input.sizeBytes,
          sha256: input.sha256,
        }),
      },
    );
    return { intent };
  } catch (error) {
    return submissionError(error);
  }
}

export async function uploadLocalSubmissionAttachment(
  attachmentId: string,
  file: File,
): Promise<SubmissionActionState> {
  if (!UUID_PATTERN.test(attachmentId) || file.size < 1 || file.size > 5 * 1024 * 1024) {
    return { error: "本地上传参数无效。" };
  }
  try {
    await apiRequest(`/api/v1/attachments/${attachmentId}/content`, "LEARNER", {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: Buffer.from(await file.arrayBuffer()),
    });
    return {};
  } catch (error) {
    return submissionError(error);
  }
}

export async function completeSubmissionAttachmentUpload(
  assignmentId: string,
  attachmentId: string,
  contentType: string,
  sizeBytes: number,
  sha256: string,
): Promise<SubmissionActionState> {
  if (!UUID_PATTERN.test(assignmentId) || !UUID_PATTERN.test(attachmentId)) {
    return { error: "附件完成参数无效。" };
  }
  try {
    await apiRequest(`/api/v1/attachments/${attachmentId}/complete`, "LEARNER", {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({ content_type: contentType, size_bytes: sizeBytes, sha256 }),
    });
  } catch (error) {
    return submissionError(error);
  }
  revalidatePath(`/app/tasks/${assignmentId}`);
  return {};
}

export async function deleteSubmissionAttachment(data: FormData) {
  const assignmentId = requiredUuid(data, "assignment_id");
  const attachmentId = requiredUuid(data, "attachment_id");
  await apiRequest(`/api/v1/attachments/${attachmentId}`, "LEARNER", { method: "DELETE" });
  revalidatePath(`/app/tasks/${assignmentId}`);
  redirect(`/app/tasks/${assignmentId}?attachment=deleted`);
}

export type ReviewActionState = {
  error?: string;
  requestId?: string;
};

function reviewError(error: unknown): ReviewActionState {
  if (error instanceof ApiRequestError) {
    return { error: error.message, requestId: error.requestId };
  }
  return { error: error instanceof Error ? error.message : "操作没有完成，请重试。" };
}

export async function startReview(
  _previousState: ReviewActionState,
  data: FormData,
): Promise<ReviewActionState> {
  let reviewId: string;
  try {
    reviewId = requiredUuid(data, "review_id");
    const expectedRevision = requiredRevision(data);
    const idempotencyKey = requiredIdempotencyKey(data, "review_idempotency_key");
    await apiRequest(`/api/v1/reviews/${reviewId}/start`, "REVIEWER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ expected_revision: expectedRevision }),
    });
  } catch (error) {
    return reviewError(error);
  }
  revalidatePath("/review");
  redirect(`/review/${reviewId}?started=yes`);
}

export async function finalizeReview(
  _previousState: ReviewActionState,
  data: FormData,
): Promise<ReviewActionState> {
  let reviewId: string;
  let overallDecision: "APPROVE" | "REQUEST_REVISION";
  try {
    reviewId = requiredUuid(data, "review_id");
    const expectedRevision = requiredRevision(data);
    const idempotencyKey = requiredIdempotencyKey(data, "review_idempotency_key");
    const decision = data.get("overall_decision");
    if (decision !== "APPROVE" && decision !== "REQUEST_REVISION") {
      throw new Error("请选择通过或要求修订。");
    }
    overallDecision = decision;
    const overallFeedback = data.get("overall_feedback");
    if (
      typeof overallFeedback !== "string"
      || overallFeedback.trim().length < 10
      || overallFeedback.length > 2_000
    ) {
      throw new Error("总体反馈需为 10–2000 个字符。");
    }
    const rubricKeys = data.getAll("rubric_dimension_key");
    if (
      rubricKeys.length < 1
      || rubricKeys.length > 6
      || rubricKeys.some(
        (key) => typeof key !== "string" || !/^[a-z][a-z0-9_]{2,59}$/.test(key),
      )
      || new Set(rubricKeys).size !== rubricKeys.length
    ) {
      throw new Error("Rubric 维度配置无效，请刷新后重试。");
    }
    const rubricEvaluations = (rubricKeys as string[]).map((dimensionKey) => {
      const rating = data.get(`${dimensionKey}_rating`);
      const feedback = data.get(`${dimensionKey}_feedback`);
      if (rating !== "MEETS" && rating !== "NEEDS_WORK") {
        throw new Error("请完成全部 Rubric 评分。");
      }
      if (typeof feedback !== "string" || feedback.trim().length < 5 || feedback.length > 500) {
        throw new Error("每个 Rubric 维度需填写 5–500 个字符的具体反馈。");
      }
      return {
        dimension_key: dimensionKey,
        rating,
        feedback: feedback.trim(),
      };
    });
    await apiRequest(`/api/v1/reviews/${reviewId}/finalize`, "REVIEWER", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        overall_decision: overallDecision,
        overall_feedback: overallFeedback.trim(),
        rubric_evaluations: rubricEvaluations,
      }),
    });
  } catch (error) {
    return reviewError(error);
  }
  revalidatePath("/review");
  redirect(`/review?finalized=${overallDecision === "APPROVE" ? "approved" : "revision"}`);
}

function requiredReason(data: FormData): string {
  const reason = data.get("reason");
  if (typeof reason !== "string" || reason.trim().length < 10 || reason.length > 500) {
    throw new Error("运营理由需为 10–500 个字符。");
  }
  return reason.trim();
}

export async function assignEnrollmentReviewer(data: FormData) {
  const enrollmentId = requiredUuid(data, "enrollment_id");
  const reviewerId = requiredUuid(data, "reviewer_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/ops/enrollments/${enrollmentId}/reviewer`, "OPERATOR", {
    method: "PUT",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: expectedRevision,
      reviewer_id: reviewerId,
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=reviewer");
}

export async function cancelEnrollment(data: FormData) {
  const enrollmentId = requiredUuid(data, "enrollment_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/ops/enrollments/${enrollmentId}/cancel`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: expectedRevision,
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=cancelled");
}

export type InviteActionState = {
  error?: string;
  requestId?: string;
  joinPath?: string;
  expiresAt?: string;
};

export async function createLearnerInvite(
  _previousState: InviteActionState,
  data: FormData,
): Promise<InviteActionState> {
  try {
    const reviewerId = requiredUuid(data, "reviewer_id");
    const journeyValue = data.get("journey_version_id");
    const taskValue = data.get("task_version_id");
    const journeyVersionId =
      typeof journeyValue === "string" && journeyValue
        ? requiredUuid(data, "journey_version_id")
        : null;
    const taskVersionId =
      typeof taskValue === "string" && taskValue
        ? requiredUuid(data, "task_version_id")
        : null;
    if ((journeyVersionId === null) === (taskVersionId === null)) {
      return { error: "请选择一个正式旅程或一个兼容任务版本。" };
    }
    const purpose = data.get("purpose");
    if (typeof purpose !== "string" || purpose.trim().length < 3 || purpose.length > 200) {
      return { error: "邀请用途需为 3–200 个字符。" };
    }
    const result = await apiRequest<{ invite_token: string; expires_at: string }>(
      "/api/v1/ops/invites",
      "OPERATOR",
      {
        method: "POST",
        headers: commandHeaders(),
        body: JSON.stringify({
          purpose: purpose.trim(),
          expires_in_hours: 24,
          role: "LEARNER",
          reviewer_id: reviewerId,
          task_version_id: taskVersionId,
          journey_version_id: journeyVersionId,
          target_user_id: null,
        }),
      },
    );
    revalidatePath("/ops");
    return {
      joinPath: `/join#token=${encodeURIComponent(result.invite_token)}`,
      expiresAt: result.expires_at,
    };
  } catch (error) {
    return submissionError(error);
  }
}

export async function publishFormalJourney(data: FormData) {
  const reviewedBy = requiredUuid(data, "reviewed_by");
  const reviewAcknowledged = data.get("review_acknowledged") === "on";
  await apiRequest("/api/v1/ops/formal-journeys/publish", "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      reviewed_by: reviewedBy,
      expected_absent: true,
      review_acknowledged: reviewAcknowledged,
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=formal-journey-published#learner-invites");
}

export async function revokeLearnerInvite(data: FormData) {
  const inviteId = requiredUuid(data, "invite_id");
  await apiRequest(`/api/v1/ops/invites/${inviteId}/revoke`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: requiredRevision(data),
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=invite-revoked#learner-invites");
}

export type LearnerReentryActionState = {
  error?: string;
  requestId?: string;
  joinPath?: string;
  expiresAt?: string;
};

export async function createLearnerReentry(
  _previousState: LearnerReentryActionState,
  data: FormData,
): Promise<LearnerReentryActionState> {
  try {
    const enrollmentId = requiredUuid(data, "enrollment_id");
    const reason = data.get("reason");
    if (typeof reason !== "string" || reason.trim().length < 10 || reason.length > 500) {
      return { error: "重新进入理由需为 10–500 个字符。" };
    }
    const result = await apiRequest<{ invite_token: string; expires_at: string }>(
      `/api/v1/ops/enrollments/${enrollmentId}/learner-reentry`,
      "OPERATOR",
      {
        method: "POST",
        headers: commandHeaders(),
        body: JSON.stringify({
          expected_revision: requiredRevision(data),
          expires_in_minutes: 30,
          reason: reason.trim(),
        }),
      },
    );
    revalidatePath("/ops");
    return {
      joinPath: `/join#token=${encodeURIComponent(result.invite_token)}`,
      expiresAt: result.expires_at,
    };
  } catch (error) {
    return submissionError(error);
  }
}

export async function configureNotificationEndpoint(data: FormData) {
  const userId = requiredUuid(data, "user_id");
  const revisionValue = Number(data.get("revision"));
  if (!Number.isSafeInteger(revisionValue) || revisionValue < 0) {
    throw new Error("通知接收人版本无效，请刷新页面后重试。");
  }
  const receiveId = data.get("receive_id");
  if (
    typeof receiveId !== "string"
    || !/^ou_[A-Za-z0-9_-]{8,120}$/.test(receiveId.trim())
  ) {
    throw new Error("请输入一个有效的飞书 open_id。");
  }
  await apiRequest(`/api/v1/ops/users/${userId}/notification-endpoint`, "OPERATOR", {
    method: "PUT",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: revisionValue,
      receive_id: receiveId.trim(),
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=notification-endpoint");
}

export async function revokeNotificationEndpoint(data: FormData) {
  const endpointId = requiredUuid(data, "endpoint_id");
  await apiRequest(
    `/api/v1/ops/notification-endpoints/${endpointId}/revoke`,
    "OPERATOR",
    {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({
        expected_revision: requiredRevision(data),
        reason: requiredReason(data),
      }),
    },
  );
  revalidatePath("/ops");
  redirect("/ops?updated=notification-endpoint-revoked");
}

export async function redriveNotificationDelivery(data: FormData) {
  const deliveryId = requiredUuid(data, "delivery_id");
  await apiRequest(
    `/api/v1/ops/notification-deliveries/${deliveryId}/redrive`,
    "OPERATOR",
    {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({
        expected_revision: requiredRevision(data),
        reason: requiredReason(data),
      }),
    },
  );
  revalidatePath("/ops");
  redirect("/ops?updated=notification-redrive");
}

export type IdentityLinkActionState = {
  error?: string;
  requestId?: string;
  startPath?: string;
  expiresAt?: string;
};

export async function createIdentityLink(
  _previousState: IdentityLinkActionState,
  data: FormData,
): Promise<IdentityLinkActionState> {
  const targetUserId = requiredUuid(data, "target_user_id");
  const role = data.get("role");
  if (role !== "REVIEWER" && role !== "OPERATOR") {
    return { error: "身份角色无效。请刷新页面后重试。" };
  }
  try {
    const result = await apiRequest<{ start_path: string; expires_at: string }>(
      "/api/v1/ops/identity-links",
      "OPERATOR",
      {
        method: "POST",
        headers: commandHeaders(),
        body: JSON.stringify({
          target_user_id: targetUserId,
          role,
          expires_in_minutes: 30,
        }),
      },
    );
    return { startPath: result.start_path, expiresAt: result.expires_at };
  } catch (error) {
    return submissionError(error);
  }
}

export async function revokeIdentityLink(data: FormData) {
  const linkId = requiredUuid(data, "link_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(`/api/v1/ops/identity-links/${linkId}/revoke`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: expectedRevision,
      reason: requiredReason(data),
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=identity-link-revoked");
}

export async function revokeExternalIdentity(data: FormData) {
  const identityId = requiredUuid(data, "identity_id");
  const expectedRevision = requiredRevision(data);
  await apiRequest(
    `/api/v1/ops/external-identities/${identityId}/revoke`,
    "OPERATOR",
    {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({
        expected_revision: expectedRevision,
        reason: requiredReason(data),
      }),
    },
  );
  revalidatePath("/ops");
  redirect("/ops?updated=external-identity-revoked");
}
