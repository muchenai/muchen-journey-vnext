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
  TaskContentInput,
} from "@/lib/server/api";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MATERIAL_KEY_PATTERN = /^[a-z0-9][a-z0-9_-]{2,79}$/;

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

function requiredText(data: FormData, key: string, min: number, max: number): string {
  const value = data.get(key);
  if (typeof value !== "string" || value.trim().length < min || value.length > max) {
    throw new Error(`${key} 内容不符合长度要求。`);
  }
  return value.trim();
}

function textLines(data: FormData, key: string, maxItems: number): string[] {
  const value = requiredText(data, key, 1, 6_000);
  const lines = value.split("\n").map((item) => item.trim()).filter(Boolean);
  if (lines.length < 1 || lines.length > maxItems || new Set(lines).size !== lines.length) {
    throw new Error(`${key} 必须是 1–${maxItems} 行不重复内容。`);
  }
  return lines;
}

function boundedInteger(data: FormData, key: string, min: number, max: number): number {
  const value = Number(data.get(key));
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new Error(`${key} 数值无效。`);
  }
  return value;
}

function taskContentFromForm(data: FormData): TaskContentInput {
  const materialKey = requiredText(data, "material_key", 3, 80);
  if (!MATERIAL_KEY_PATTERN.test(materialKey)) throw new Error("材料稳定编号无效。");
  const optionalUrlValue = data.get("link_url");
  const optionalUrl = typeof optionalUrlValue === "string" ? optionalUrlValue.trim() : "";
  if (optionalUrl && !/^https:\/\/[^\s]+$/.test(optionalUrl)) {
    throw new Error("外部材料必须使用 HTTPS 链接。");
  }
  const learningMaterials: TaskContentInput["learning_materials"] = [
    {
      key: materialKey,
      title: requiredText(data, "material_title", 2, 160),
      kind: "TEXT" as const,
      source_label: requiredText(data, "material_source", 2, 160),
      body: requiredText(data, "material_body", 20, 20_000),
      url: null,
      estimated_duration_minutes: boundedInteger(data, "material_duration", 1, 120),
      required: true,
    },
  ];
  if (optionalUrl) {
    const linkKey = requiredText(data, "link_key", 3, 80);
    if (!MATERIAL_KEY_PATTERN.test(linkKey) || linkKey === materialKey) {
      throw new Error("外部材料稳定编号无效或重复。");
    }
    learningMaterials.push({
      key: linkKey,
      title: requiredText(data, "link_title", 2, 160),
      kind: "HTTPS_LINK",
      source_label: requiredText(data, "link_source", 2, 160),
      body: null,
      url: optionalUrl,
      estimated_duration_minutes: boundedInteger(data, "link_duration", 1, 120),
      required: true,
    });
  }
  return {
    title: requiredText(data, "title", 3, 180),
    purpose: requiredText(data, "purpose", 10, 2_000),
    learner_outcome: requiredText(data, "learner_outcome", 10, 2_000),
    instructions: textLines(data, "instructions", 12),
    completion_criteria: textLines(data, "completion_criteria", 12),
    required_deliverables: textLines(data, "required_deliverables", 12),
    content_source_notes: textLines(data, "content_source_notes", 20),
    change_summary: requiredText(data, "change_summary", 10, 1_000),
    reviewer_calibration_note: requiredText(data, "reviewer_calibration_note", 10, 1_000),
    allowed_attachment_types: [],
    max_attachment_size_bytes: 0,
    reference_materials: [],
    learning_materials: learningMaterials,
    estimated_duration_minutes: boundedInteger(data, "estimated_duration_minutes", 1, 480),
    rubric: {
      version: 1,
      dimensions: [{
        dimension_key: "evidence_traceability",
        title: requiredText(data, "rubric_title", 2, 80),
        purpose: requiredText(data, "rubric_purpose", 5, 500),
        evidence_expected: requiredText(data, "rubric_evidence", 5, 500),
        levels: {
          MEETS: requiredText(data, "rubric_meets", 1, 500),
          NEEDS_WORK: requiredText(data, "rubric_needs_work", 1, 500),
        },
        required: true,
        feedback_prompt: requiredText(data, "rubric_feedback_prompt", 5, 500),
        blocking_rule: "REQUIRE_FEEDBACK",
      }],
    },
    reviewer_role: "REVIEWER",
    feedback_sla_business_days: boundedInteger(data, "feedback_sla_business_days", 1, 10),
    sensitivity: "INTERNAL",
    audience: "LEARNER",
  };
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

export async function acceptInvite(data: FormData) {
  const token = data.get("token");
  const displayName = data.get("display_name");
  const acceptedPurpose = data.get("accepted_purpose") === "yes";
  if (typeof token !== "string" || token.length < 32 || token.length > 256) {
    redirect("/join?code=INVITE_EXPIRED_OR_REVOKED");
  }
  if (
    displayName !== null
    && (typeof displayName !== "string" || !displayName.trim() || displayName.length > 120)
  ) {
    redirect("/join?code=VALIDATION_FAILED");
  }
  if (!acceptedPurpose) redirect("/join?code=PURPOSE_NOT_ACCEPTED");

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
  const joinMaxAge = Math.max(
    1,
    Math.floor((new Date(exchange.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const joinOptions = {
    path: "/",
    sameSite: "lax" as const,
    secure: cookieSecure(),
    maxAge: joinMaxAge,
  };
  cookieStore.set(JOIN_COOKIE, joinToken, { ...joinOptions, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, exchange.data.csrf_token, { ...joinOptions, httpOnly: false });
  cookieStore.set(
    JOIN_SUMMARY_COOKIE,
    Buffer.from(JSON.stringify(exchange.data)).toString("base64url"),
    { ...joinOptions, httpOnly: true },
  );

  let confirmation: {
    data: { expires_at: string; csrf_token: string };
    setCookies: string[];
  };
  try {
    confirmation = await anonymousApiRequest("/api/v1/identity/confirm", {
      method: "POST",
      headers: {
        Cookie: `${JOIN_COOKIE}=${joinToken}; ${CSRF_COOKIE}=${exchange.data.csrf_token}`,
        "X-CSRF-Token": exchange.data.csrf_token,
      },
      body: JSON.stringify({
        display_name: exchange.data.flow === "JOIN" && typeof displayName === "string"
          ? displayName.trim()
          : null,
        accepted_purpose: true,
        return_to: "/app",
      }),
    });
  } catch (error) {
    safeJoinError(error);
  }

  const sessionToken = cookieValue(confirmation.setCookies, SESSION_COOKIE);
  if (!sessionToken) throw new Error("API 未返回安全 vNext 会话。");
  const sessionMaxAge = Math.max(
    1,
    Math.floor((new Date(confirmation.data.expires_at).getTime() - Date.now()) / 1000),
  );
  const sessionOptions = {
    path: "/",
    sameSite: "lax" as const,
    secure: cookieSecure(),
    maxAge: sessionMaxAge,
  };
  cookieStore.set(SESSION_COOKIE, sessionToken, { ...sessionOptions, httpOnly: true });
  cookieStore.set(CSRF_COOKIE, confirmation.data.csrf_token, {
    ...sessionOptions,
    httpOnly: false,
  });
  cookieStore.delete(JOIN_COOKIE);
  cookieStore.delete(JOIN_SUMMARY_COOKIE);
  revalidatePath("/app");
  redirect("/app");
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

export async function completeLearningMaterial(data: FormData) {
  const assignmentId = requiredUuid(data, "assignment_id");
  const materialKey = data.get("material_key");
  const taskVersion = Number(data.get("task_version"));
  const idempotencyKey = requiredIdempotencyKey(data, "idempotency_key");
  if (typeof materialKey !== "string" || !MATERIAL_KEY_PATTERN.test(materialKey)) {
    throw new Error("学习材料标识无效。请刷新页面后重试。");
  }
  if (!Number.isSafeInteger(taskVersion) || taskVersion < 1) {
    throw new Error("学习材料版本无效。请刷新页面后重试。");
  }
  await apiRequest(
    `/api/v1/me/assignments/${assignmentId}/materials/${encodeURIComponent(materialKey)}/complete`,
    "LEARNER",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ task_version: taskVersion }),
    },
  );
  revalidatePath(`/app/tasks/${assignmentId}`);
  revalidatePath("/app");
  redirect(`/app/tasks/${assignmentId}?material=completed`);
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
      const scoreValue = data.get(`${dimensionKey}_score`);
      const feedback = data.get(`${dimensionKey}_feedback`);
      if (rating !== "MEETS" && rating !== "NEEDS_WORK") {
        throw new Error("请完成全部 Rubric 评分。");
      }
      if (typeof feedback !== "string" || feedback.trim().length < 5 || feedback.length > 500) {
        throw new Error("每个 Rubric 维度需填写 5–500 个字符的具体反馈。");
      }
      const score = typeof scoreValue === "string" && scoreValue !== ""
        ? Number(scoreValue)
        : null;
      if (score !== null && (!Number.isInteger(score) || score < 0 || score > 15)) {
        throw new Error("Rubric 分数必须是 0–15 的整数。");
      }
      return {
        dimension_key: dimensionKey,
        rating,
        score,
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

export type PublishFormalJourneyActionState = SubmissionActionState;

export async function publishFormalJourney(
  _previousState: PublishFormalJourneyActionState,
  data: FormData,
): Promise<PublishFormalJourneyActionState> {
  try {
    const reviewedBy = requiredUuid(data, "reviewed_by");
    const expectedCurrentVersion = Number(data.get("expected_current_version"));
    if (!Number.isInteger(expectedCurrentVersion) || expectedCurrentVersion < 0) {
      throw new Error("当前旅程版本无效，请刷新后重试。");
    }
    const reviewAcknowledged = data.get("review_acknowledged") === "on";
    await apiRequest("/api/v1/ops/formal-journeys/publish", "OPERATOR", {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({
        reviewed_by: reviewedBy,
        catalog_version: 2,
        expected_current_version: expectedCurrentVersion,
        review_acknowledged: reviewAcknowledged,
      }),
    });
  } catch (error) {
    return submissionError(error);
  }
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

export async function updateInvitationControl(data: FormData) {
  const target = data.get("target_state");
  if (target !== "FROZEN" && target !== "OPEN") {
    throw new Error("邀请控制目标状态无效。");
  }
  await apiRequest(
    `/api/v1/ops/invitation-control/${target === "FROZEN" ? "freeze" : "resume"}`,
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
  redirect(`/ops?updated=invites-${target === "FROZEN" ? "frozen" : "resumed"}#learner-invites`);
}

type AdmissionScores = {
  attendance_discipline: number;
  muchener_understanding: number;
  ai_data_fundamentals: number;
  project_organization_fit: number;
};

export type AdmissionPreviewActionState = SubmissionActionState & {
  enrollmentId?: string;
  scores?: AdmissionScores;
  totalScore?: number;
  recommendationTier?: "A" | "B" | "C" | "D";
  recommendedDecision?: "ADMIT" | "DEFER" | "NOT_ADMIT";
};

function admissionScores(data: FormData): AdmissionScores {
  const read = (key: keyof AdmissionScores) => {
    const value = Number(data.get(key));
    if (!Number.isInteger(value) || value < 0 || value > 10) {
      throw new Error("四项人工观察分必须是 0–10 的整数。");
    }
    return value;
  };
  return {
    attendance_discipline: read("attendance_discipline"),
    muchener_understanding: read("muchener_understanding"),
    ai_data_fundamentals: read("ai_data_fundamentals"),
    project_organization_fit: read("project_organization_fit"),
  };
}

export async function previewFormalAdmission(
  _previousState: AdmissionPreviewActionState,
  data: FormData,
): Promise<AdmissionPreviewActionState> {
  try {
    const enrollmentId = requiredUuid(data, "enrollment_id");
    const scores = admissionScores(data);
    const preview = await apiRequest<{
      total_score: number;
      recommendation_tier: "A" | "B" | "C" | "D";
      recommended_decision: "ADMIT" | "DEFER" | "NOT_ADMIT";
    }>(`/api/v1/ops/enrollments/${enrollmentId}/formal-admission/preview`, "OPERATOR", {
      method: "POST",
      body: JSON.stringify({ scores }),
    });
    return {
      enrollmentId,
      scores,
      totalScore: preview.total_score,
      recommendationTier: preview.recommendation_tier,
      recommendedDecision: preview.recommended_decision,
    };
  } catch (error) {
    return submissionError(error);
  }
}

export async function createFormalAdmissionDecision(data: FormData) {
  const enrollmentId = requiredUuid(data, "enrollment_id");
  const decision = data.get("decision");
  if (!["ADMIT", "DEFER", "NOT_ADMIT"].includes(String(decision))) {
    throw new Error("请选择人工准入结论。");
  }
  const scoreEvidence = data.get("score_evidence");
  const decisionReason = data.get("decision_reason");
  const overrideValue = data.get("override_reason");
  if (typeof scoreEvidence !== "string" || scoreEvidence.trim().length < 20) {
    throw new Error("请记录至少 20 个字符的人工评分证据。");
  }
  if (typeof decisionReason !== "string" || decisionReason.trim().length < 20) {
    throw new Error("请记录至少 20 个字符的人工决定理由。");
  }
  const overrideReason = typeof overrideValue === "string" && overrideValue.trim()
    ? overrideValue.trim()
    : null;
  await apiRequest(`/api/v1/ops/enrollments/${enrollmentId}/formal-admission`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_absent: true,
      human_judgement_acknowledged: data.get("human_judgement_acknowledged") === "on",
      scores: admissionScores(data),
      score_evidence: scoreEvidence.trim(),
      decision,
      decision_reason: decisionReason.trim(),
      override_reason: overrideReason,
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=formal-admission-decided#admission-decisions");
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
      joinPath: `/join#token=${encodeURIComponent(result.invite_token)}&flow=reentry`,
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

export async function createContentDraft(data: FormData) {
  const taskDefinitionId = requiredUuid(data, "task_definition_id");
  const result = await apiRequest<{ id: string }>(
    `/api/v1/content/task-definitions/${taskDefinitionId}/drafts`,
    "CONTENT_EDITOR",
    {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({ content: taskContentFromForm(data) }),
    },
  );
  revalidatePath("/content");
  redirect(`/content/drafts/${result.id}?updated=created`);
}

export async function updateContentDraft(data: FormData) {
  const draftId = requiredUuid(data, "draft_id");
  await apiRequest(`/api/v1/content/drafts/${draftId}`, "CONTENT_EDITOR", {
    method: "PUT",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: requiredRevision(data),
      content: taskContentFromForm(data),
    }),
  });
  revalidatePath("/content");
  revalidatePath(`/content/drafts/${draftId}`);
  redirect(`/content/drafts/${draftId}?updated=saved`);
}

export async function submitContentDraft(data: FormData) {
  const draftId = requiredUuid(data, "draft_id");
  await apiRequest(`/api/v1/content/drafts/${draftId}/submit`, "CONTENT_EDITOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: requiredRevision(data),
      review_note: requiredText(data, "review_note", 10, 1_000),
    }),
  });
  revalidatePath("/content");
  revalidatePath(`/content/drafts/${draftId}`);
  redirect(`/content/drafts/${draftId}?updated=submitted`);
}

export async function publishContentDraft(data: FormData) {
  const draftId = requiredUuid(data, "draft_id");
  const reviewerId = requiredUuid(data, "reviewer_id");
  const definitionRevision = Number(data.get("definition_revision"));
  if (!Number.isSafeInteger(definitionRevision) || definitionRevision < 1) {
    throw new Error("任务定义版本无效，请刷新页面重试。");
  }
  if (data.get("review_acknowledged") !== "on") {
    throw new Error("发布前必须确认复核已完成。近似确认不能替代真实复核。");
  }
  const verifiedMaterialUrls = data.getAll("verified_material_url").map((value) => {
    if (typeof value !== "string" || !value.startsWith("https://") || value.length > 2_000) {
      throw new Error("材料链接确认值无效，请刷新页面重新逐项打开。");
    }
    return value;
  });
  await apiRequest(`/api/v1/ops/content-drafts/${draftId}/publish`, "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      expected_revision: requiredRevision(data),
      expected_definition_revision: definitionRevision,
      reviewed_by: reviewerId,
      review_acknowledged: true,
      verified_material_urls: verifiedMaterialUrls,
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=content-draft-published#content-drafts");
}

export async function createContentEditor(data: FormData) {
  const displayName = requiredText(data, "display_name", 1, 120);
  await apiRequest("/api/v1/ops/content-editors", "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({ display_name: displayName, expected_absent: true }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=content-editor-created#identity-access");
}

export async function assembleFormalJourneyV3(data: FormData) {
  const reviewerId = requiredUuid(data, "reviewer_id");
  const expectedCurrentVersion = Number(data.get("expected_current_version"));
  const taskVersionIds = data.getAll("task_version_id");
  if (
    !Number.isSafeInteger(expectedCurrentVersion)
    || expectedCurrentVersion < 1
    || taskVersionIds.length !== 8
    || taskVersionIds.some((value) => typeof value !== "string" || !UUID_PATTERN.test(value))
    || new Set(taskVersionIds).size !== 8
  ) {
    throw new Error("Journey V3 固定版本清单无效，请刷新后重试。");
  }
  if (data.get("review_acknowledged") !== "on") {
    throw new Error("必须确认八站内容和顺序已经完成线下复核。");
  }
  await apiRequest("/api/v1/ops/formal-journeys/assemble-v3", "OPERATOR", {
    method: "POST",
    headers: commandHeaders(),
    body: JSON.stringify({
      reviewed_by: reviewerId,
      expected_current_version: expectedCurrentVersion,
      task_version_ids: taskVersionIds,
      content_review_note: requiredText(data, "content_review_note", 20, 1_000),
      review_acknowledged: true,
    }),
  });
  revalidatePath("/ops");
  redirect("/ops?updated=journey-v3-assembled#journey-v3");
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
  if (role !== "REVIEWER" && role !== "OPERATOR" && role !== "CONTENT_EDITOR") {
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

export async function transferRevokedExternalIdentity(data: FormData) {
  const identityId = requiredUuid(data, "identity_id");
  const targetUserId = requiredUuid(data, "target_user_id");
  if (data.get("target_role") !== "CONTENT_EDITOR") {
    throw new Error("仅允许迁移到已确认的 Content Editor。");
  }
  if (data.get("ownership_confirmed") !== "on") {
    throw new Error("必须确认历史飞书账号归目标 Content Editor 本人所有。");
  }
  await apiRequest(
    `/api/v1/ops/external-identities/${identityId}/transfer-revoked`,
    "OPERATOR",
    {
      method: "POST",
      headers: commandHeaders(),
      body: JSON.stringify({
        target_user_id: targetUserId,
        target_role: "CONTENT_EDITOR",
        expected_revision: requiredRevision(data),
        reason: requiredReason(data),
      }),
    },
  );
  revalidatePath("/ops");
  redirect("/ops?updated=external-identity-transferred#identity-access");
}
