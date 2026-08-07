import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";

export { CSRF_COOKIE, JOIN_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";

export type Role = "LEARNER" | "REVIEWER" | "OPERATOR" | "CONTENT_EDITOR";

export type CurrentAction = {
  action_type: string;
  stage: string;
  resource_id: string;
  title: string;
  reason: string;
  allowed_commands: string[];
  revision: number;
  responsible_party: string;
  feedback_expectation: string;
  journey: JourneyProgress | null;
};

export type JourneyProgressNode = {
  stable_key: string;
  position: number;
  stage_kind: "DAY_0" | "TREASURE" | "ASSESSMENT";
  completion_policy: "LEARNER_EVIDENCE" | "REVIEW_REQUIRED";
  title: string;
  short_description: string;
  status: "COMPLETED" | "CURRENT" | "LOCKED";
  assignment_id: string;
};

export type JourneyProgress = {
  journey_version_id: string;
  stable_key: string;
  version: number;
  title: string;
  completed_stages: number;
  total_stages: 8;
  current_stage_key: string | null;
  nodes: JourneyProgressNode[];
};

export type LearningExperience = {
  mode:
    | "ORIENTATION"
    | "LEARN_AND_REFLECT"
    | "LEARN_AND_CHECK"
    | "CASE_STUDY"
    | "ROLE_PRACTICE"
    | "ASSESSMENT";
  version: number;
  schedule: {
    start: string;
    end: string;
    break_after?: string;
  };
  learning_blocks: Array<{
    kind: string;
    title: string;
    body: string;
  }>;
  knowledge_checks: string[];
  response_sections: string[];
};

export type Assignment = {
  id: string;
  status: string;
  revision: number;
  allowed_commands: string[];
  stable_task_key: string;
  task_version: number;
  task_title: string;
  task_purpose: string;
  learner_outcome: string;
  instructions: string[];
  completion_criteria: string[];
  required_deliverables: string[];
  allowed_attachment_types: string[];
  max_attachment_size_bytes: number;
  reference_materials: string[];
  learning_materials: LearningMaterial[];
  learning_experience: LearningExperience | Record<string, never>;
  estimated_duration_minutes: number;
  feedback_sla_business_days: number;
  rubric: {
    version: number;
    dimensions: Array<{
      dimension_key: string;
      title: string;
      evidence_expected: string;
      max_points?: number;
      meets_threshold?: number;
      score_category?: string;
    }>;
  };
  submission: Submission | null;
  draft: SubmissionDraft | null;
  available_attachments: Attachment[];
  latest_revision_feedback: string | null;
  journey_stage: Omit<
    JourneyProgressNode,
    "status" | "assignment_id"
  > | null;
};

export type LearningMaterial = {
  key: string;
  title: string;
  kind: "TEXT" | "HTTPS_LINK";
  source_label: string;
  body: string | null;
  url: string | null;
  estimated_duration_minutes: number;
  required: boolean;
  completed_at: string | null;
};

export type Attachment = {
  id: string;
  assignment_id: string;
  purpose: "SUBMISSION_EVIDENCE";
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: string;
  scan_status: string;
};

export type SubmissionVersion = {
  id: string;
  version_no: number;
  body: string;
  created_at: string;
  attachments: Attachment[];
  review_id: string | null;
  review_status: string | null;
  decision: string | null;
  feedback: string | null;
};

export type Submission = {
  id: string;
  assignment_id: string;
  current_version_no: number;
  versions: SubmissionVersion[];
};

export type SubmissionDraft = {
  body: string;
  attachment_ids: string[];
  revision: number;
  updated_at: string;
  idempotency_replay: boolean;
};

export type ReviewItem = {
  id: string;
  assignment_id: string;
  submission_id: string;
  submission_version_id: string;
  status: string;
  revision: number;
  allowed_commands: string[];
  learner_name: string;
  task_title: string;
  task_version: number;
  submission_version_no: number;
  assigned_at: string;
  started_at: string | null;
  priority_reason: string;
  material_status: "COMPLETE" | "INCOMPLETE";
};

export type ReviewDetail = ReviewItem & {
  submission_body: string;
  task_purpose: string;
  completion_criteria: string[];
  required_deliverables: string[];
  rubric: {
    version: number;
    dimensions: Array<{
      dimension_key: string;
      title: string;
      evidence_expected: string;
      required: boolean;
      max_points?: number;
      meets_threshold?: number;
      score_category?: string;
    }>;
  };
  materials: {
    status: "COMPLETE" | "INCOMPLETE";
    missing_items: string[];
    required_deliverables: string[];
    attachments: Array<{
      id: string;
      original_filename: string;
      content_type: string;
      size_bytes: number;
      status: string;
      scan_status: string;
      download_path: string;
    }>;
  };
  finalized_at: string | null;
  evaluation: {
    id: string;
    decision: "PASS" | "REVISION_REQUIRED";
    overall_decision: "APPROVE" | "REQUEST_REVISION";
    overall_feedback: string;
    rubric_evaluations: Array<{
      dimension_key: string;
      rating: "MEETS" | "NEEDS_WORK";
      score: number | null;
      feedback: string | null;
    }>;
    feedback_structure_version: number;
    reviewer_id: string;
    review_revision: number;
    created_at: string;
  } | null;
};

export type Result = {
  outcome_id: string;
  status: string;
  decision: "PASS";
  summary: string;
  learning_completion: {
    status: "COMPLETED";
    completed_stages: number;
    total_stages: number;
  };
  reviewer_conclusion: {
    status: "FINALIZED";
    decision: "PASS";
    reviewer_id: string;
    overall_feedback: string;
    concluded_at: string;
  };
  system_recommendation: {
    status: "PENDING_OPERATOR_INPUT" | "RECORDED";
    advisory_only: true;
    recommendation_tier: "A" | "B" | "C" | "D" | null;
    recommended_decision: "ADMIT" | "DEFER" | "NOT_ADMIT" | null;
  };
  operator_admission: {
    status: "PENDING" | "DECIDED";
    decision: "ADMIT" | "DEFER" | "NOT_ADMIT" | null;
    decision_reason: string | null;
    total_score: number | null;
    decided_at: string | null;
  };
  evaluation: {
    id: string;
    reviewer_id: string;
    decision: "PASS";
    overall_feedback: string;
    rubric_feedback: Array<{
      dimension_key: string;
      title: string;
      rating: string;
      feedback: string | null;
    }>;
    created_at: string;
  };
  journey_evaluations: Array<{
    id: string;
    reviewer_id: string;
    decision: "PASS";
    overall_feedback: string;
    rubric_feedback: Array<{
      dimension_key: string;
      title: string;
      rating: string;
      feedback: string | null;
    }>;
    created_at: string;
    stage_key: string;
    stage_title: string;
  }>;
  handoff: {
    id: string;
    status: "READY";
    owner_user_id: string;
    owner_display_name: string;
    title: string;
    next_step_code: "CONFIRM_HANDOFF";
    next_step_title: string;
    instructions: string;
    created_at: string;
  };
  notification: {
    status: string;
    channel: string | null;
    display_status: string;
    attempt_count: number;
    next_attempt_at: string | null;
    last_error_code: string | null;
    delivered_at: string | null;
    delivery_scope: "LOCAL_TEST_ONLY" | "FEISHU";
    external_delivery_confirmed: boolean;
  };
  ai_summary: {
    status: "NOT_ENABLED";
    message: string;
  };
  created_at: string;
};

export type TimelineItem = {
  item_id: string;
  event_type: string;
  title: string;
  occurred_at: string;
  object_type: string;
  object_id: string;
  details: Record<string, string | number | boolean | null>;
};

export type Timeline = {
  items: TimelineItem[];
  next_cursor: string | null;
};

export type OpsTaskDefinition = {
  id: string;
  stable_key: string;
  status: string;
  revision: number;
  content_owner_id: string;
  versions: Array<{ id: string; version: number; title: string; published_at: string }>;
};

export type LearningMaterialInput = {
  key: string;
  title: string;
  kind: "TEXT" | "HTTPS_LINK";
  source_label: string;
  body: string | null;
  url: string | null;
  estimated_duration_minutes: number;
  required: boolean;
};

export type TaskContentInput = {
  title: string;
  purpose: string;
  learner_outcome: string;
  instructions: string[];
  completion_criteria: string[];
  required_deliverables: string[];
  content_source_notes: string[];
  change_summary: string;
  reviewer_calibration_note: string;
  allowed_attachment_types: string[];
  max_attachment_size_bytes: number;
  reference_materials: string[];
  learning_materials: LearningMaterialInput[];
  estimated_duration_minutes: number;
  rubric: {
    version: 1;
    dimensions: Array<{
      dimension_key: string;
      title: string;
      purpose: string;
      evidence_expected: string;
      levels: { MEETS: string; NEEDS_WORK: string };
      required: true;
      feedback_prompt: string;
      blocking_rule: "REQUIRE_FEEDBACK";
      max_points?: number | null;
      meets_threshold?: number | null;
      score_category?: string | null;
    }>;
  };
  reviewer_role: "REVIEWER";
  feedback_sla_business_days: number;
  sensitivity: "INTERNAL";
  audience: "LEARNER";
};

export type ContentDraft = {
  id: string;
  task_definition_id: string;
  stable_key: string;
  owner_id: string;
  status: "DRAFT" | "SUBMITTED" | "PUBLISHED";
  revision: number;
  content: TaskContentInput;
  submitted_at: string | null;
  published_at: string | null;
  published_task_version_id: string | null;
};

export type OpsEnrollment = {
  id: string;
  learner_id: string;
  learner_display_name: string;
  reviewer_id: string;
  reviewer_display_name: string;
  status: string;
  revision: number;
  journey_version_id: string | null;
  assignment_statuses: string[];
  open_review_status: string | null;
  admission_decision_id: string | null;
  admission_total_score: number | null;
  admission_tier: "A" | "B" | "C" | "D" | null;
  admission_decision: "ADMIT" | "DEFER" | "NOT_ADMIT" | null;
  allowed_commands: string[];
};

export type OpsIdentityAccess = {
  user_id: string;
  display_name: string;
  role: "REVIEWER" | "OPERATOR" | "CONTENT_EDITOR";
  identity_id: string | null;
  identity_status: "UNLINKED" | "LINKED" | "REVOKED";
  identity_revision: number | null;
  identity_verified_at: string | null;
  is_current_actor: boolean;
  link_id: string | null;
  link_status: string | null;
  link_revision: number | null;
  link_expires_at: string | null;
  allowed_commands: Array<
    "create_identity_link" | "revoke_identity_link" | "revoke_external_identity"
  >;
};

export type OpsRevokedIdentityTransferCandidate = {
  identity_id: string;
  identity_revision: number;
  source_user_id: string;
  source_display_name: string;
  source_roles: Array<"REVIEWER" | "OPERATOR" | "CONTENT_EDITOR">;
  revoked_at: string;
  active_session_count: number;
};

export type OpsInvite = {
  id: string;
  purpose: string;
  role: "LEARNER";
  status: "ACTIVE" | "CONSUMED" | "EXPIRED" | "REVOKED";
  expires_at: string;
  revision: number;
  journey_version_id: string | null;
};

export type OpsInvitationControl = {
  state: "OPEN" | "FROZEN";
  new_invites_enabled: boolean;
  revision: number;
  reason: string | null;
  updated_at: string | null;
};

export type OpsFormalJourney = {
  id: string;
  stable_key: string;
  version: number;
  title: string;
  purpose: string;
  change_summary: string;
  content_review_note: string;
  published_at: string;
  stages: Array<{
    id: string;
    stable_key: string;
    position: number;
    stage_kind: "DAY_0" | "TREASURE" | "ASSESSMENT";
    completion_policy: "LEARNER_EVIDENCE" | "REVIEW_REQUIRED";
    task_version_id: string;
    title: string;
    short_description: string;
  }>;
};

export type OpsAuditEntry = {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  result: string;
  request_id: string;
  safe_details: Record<string, string | number | boolean>;
  redacted_fields: string[];
  occurred_at: string;
};

export type OpsNotificationEndpoint = {
  id: string;
  user_id: string;
  channel: "FEISHU";
  receive_id_type: "open_id";
  status: "ACTIVE" | "REVOKED";
  source: "OPERATOR_CONFIG";
  revision: number;
  updated_at: string;
};

export type OpsNotificationDelivery = {
  id: string;
  recipient_user_id: string;
  channel: string;
  status: string;
  attempt_count: number;
  redrive_count: number;
  revision: number;
  last_error_code: string | null;
  next_attempt_at: string | null;
  delivered_at: string | null;
  external_receipt_recorded: boolean;
};

export type RuntimeStatus = {
  environment: "local" | "test" | "staging" | "production";
  release: string;
  config_schema_version: 3;
  migration_revision: string;
  api: { status: string; release: string | null };
  database: { status: string };
  worker: {
    status: string;
    release: string | null;
    last_seen_at: string | null;
    stale: boolean | null;
  };
  observability_mode: "STRUCTURED_STDOUT";
  external_observability_confirmed: false;
  metrics: {
    outbox_backlog: number;
    notification_retry_wait: number;
    notification_dead: number;
    oldest_pending_seconds: number;
    permission_denials_24h: number;
  };
};

type Envelope<T> = { data: T; request_id: string };
type ErrorEnvelope = {
  error: { code: string; message: string; details?: Record<string, unknown> };
  request_id: string;
};

export class ApiRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function assertFixtureBoundary() {
  const allowed = process.env.ALLOW_FIXTURE_IDENTITY === "true";
  const environment = process.env.APP_ENV ?? "local";
  if (!allowed || !["local", "test"].includes(environment)) {
    throw new Error("Fixture identity is disabled outside local/test environments.");
  }
}

export async function apiRequest<T>(
  path: string,
  role: Role,
  init: RequestInit = {},
): Promise<T> {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get(SESSION_COOKIE)?.value;
  const csrfToken = cookieStore.get(CSRF_COOKIE)?.value;
  const requestHeaders = new Headers(init.headers);
  requestHeaders.set("Accept", "application/json");
  if (!requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }
  if (sessionToken) {
    const cookieParts = [`${SESSION_COOKIE}=${sessionToken}`];
    if (csrfToken) cookieParts.push(`${CSRF_COOKIE}=${csrfToken}`);
    requestHeaders.set("Cookie", cookieParts.join("; "));
    const method = (init.method ?? "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
      requestHeaders.set("X-CSRF-Token", csrfToken);
    }
  } else {
    assertFixtureBoundary();
    requestHeaders.set("X-Fixture-Role", role);
  }
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers: requestHeaders,
  });
  const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
  if (!response.ok || "error" in payload) {
    const code = "error" in payload ? payload.error.code : "INVALID_RESPONSE";
    const message = "error" in payload ? payload.error.message : "请求失败";
    throw new ApiRequestError(code, message, payload.request_id, response.status);
  }
  return payload.data;
}

export async function identityPageRequest<T>(
  path: string,
  role: "REVIEWER" | "OPERATOR" | "CONTENT_EDITOR",
): Promise<T> {
  try {
    return await apiRequest<T>(path, role);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 401) {
      const returnTo = role === "REVIEWER"
        ? "/review"
        : role === "CONTENT_EDITOR"
          ? "/content"
          : "/ops";
      const query = new URLSearchParams({
        auth_error: "SESSION_EXPIRED",
        return_to: returnTo,
      });
      redirect(`/?${query.toString()}`);
    }
    throw error;
  }
}

export async function learnerPageRequest<T>(path: string): Promise<T> {
  const cookieStore = await cookies();
  if (!cookieStore.get(SESSION_COOKIE)?.value) {
    redirect("/?auth_error=LEARNER_SESSION_EXPIRED");
  }
  try {
    return await apiRequest<T>(path, "LEARNER");
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 401) {
      redirect("/?auth_error=LEARNER_SESSION_EXPIRED");
    }
    throw error;
  }
}

export async function anonymousApiRequest<T>(
  path: string,
  init: RequestInit,
): Promise<{ data: T; setCookies: string[] }> {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const requestHeaders = new Headers(init.headers);
  requestHeaders.set("Accept", "application/json");
  requestHeaders.set("Content-Type", "application/json");
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers: requestHeaders,
  });
  const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
  if (!response.ok || "error" in payload) {
    const code = "error" in payload ? payload.error.code : "INVALID_RESPONSE";
    const message = "error" in payload ? payload.error.message : "请求失败";
    throw new ApiRequestError(code, message, payload.request_id, response.status);
  }
  const responseHeaders = response.headers as Headers & { getSetCookie?: () => string[] };
  const combined = response.headers.get("set-cookie");
  const setCookies = responseHeaders.getSetCookie?.() ?? (combined ? [combined] : []);
  return { data: payload.data, setCookies };
}

export function cookieValue(setCookies: string[], name: string): string | undefined {
  const prefix = `${name}=`;
  for (const header of setCookies) {
    const start = header.indexOf(prefix);
    if (start >= 0) {
      return header.slice(start + prefix.length).split(";", 1)[0];
    }
  }
  return undefined;
}

export async function hasVNextSession(): Promise<boolean> {
  return Boolean((await cookies()).get(SESSION_COOKIE)?.value);
}
