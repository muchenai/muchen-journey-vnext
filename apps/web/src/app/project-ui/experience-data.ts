import "server-only";
import { redirect } from "next/navigation";

import type { Assignment, CurrentAction } from "@/lib/server/api";
import { learnerPageRequest } from "@/lib/server/api";
import type { ProjectExperienceData } from "./types";
import { collectReviewFeedback } from "./review-feedback";
import { learnerMaterialDestinations } from "./exploration-links";

export async function loadProjectExperience(assignmentId?: string, allowPendingNickname = false): Promise<{
  learnerName: string;
  needsNickname: boolean;
  experience: ProjectExperienceData | null;
}> {
  const profile = await learnerPageRequest<{ needs_nickname: boolean }>("/api/v1/me/learner-profile");
  if (profile.needs_nickname && !allowPendingNickname) redirect("/app/profile");
  const [identity, action, completionCode] = await Promise.all([
    learnerPageRequest<{ display_name: string }>("/api/v1/session"),
    learnerPageRequest<CurrentAction>("/api/v1/me/current-action"),
    learnerPageRequest<ProjectExperienceData["completionCode"]>("/api/v1/me/completion-code"),
  ]);
  // This learner release opens only the exploration journey. A saved link to
  // another module must not render its task in the exploration interface.
  const exploration = action.journey?.stable_key.toLowerCase().replaceAll("_", "-") === "exploration-camp";
  if (assignmentId && (!exploration || !action.journey?.nodes.some(node => node.assignment_id === assignmentId))) {
    redirect("/app?view=dashboard&notice=module-designing");
  }
  if (action.journey && !exploration) {
    return { learnerName: identity.display_name, needsNickname: profile.needs_nickname, experience: null };
  }
  const resolvedAssignmentId = assignmentId
    ?? (["START_OR_CONTINUE_TASK", "REVISE_SUBMISSION", "WAIT_FOR_REVIEW"].includes(action.action_type)
      ? action.resource_id
      : action.journey?.nodes.find(node => node.status === "CURRENT")?.assignment_id ?? action.journey?.nodes.at(-1)?.assignment_id);
  if (!resolvedAssignmentId) {
    return { learnerName: identity.display_name, needsNickname: profile.needs_nickname, experience: null };
  }
  const assignment = await learnerPageRequest<Assignment>(
    `/api/v1/me/assignments/${encodeURIComponent(resolvedAssignmentId)}`,
  );
  const latestSubmission = assignment.submission?.versions.at(-1) ?? null;
  const journeyNode = action.journey?.nodes.find((node) => node.assignment_id === assignment.id);
  // Current action advances after submission; pending reviews and feedback
  // must include earlier stages rather than only the newly selected task.
  const activityAssignments = await Promise.all((action.journey?.nodes ?? [])
    .filter(node => node.assignment_status && !["AVAILABLE", "CANCELLED"].includes(node.assignment_status))
    .map(async node => ({ node, detail: node.assignment_id === assignment.id ? assignment
      : await learnerPageRequest<Assignment>(`/api/v1/me/assignments/${encodeURIComponent(node.assignment_id)}`) })));
  const activityRecords = activityAssignments.flatMap(({ node, detail }) => {
    const latest = detail.submission?.versions.at(-1);
    if (!latest) return [];
    return [{ assignmentId: detail.id, position: node.position + 1, status: detail.status,
      body: latest.body, submittedAt: latest.created_at,
      feedback: latest.feedback, feedbackAt: latest.review_finalized_at }];
  });
  return {
    learnerName: identity.display_name,
    needsNickname: profile.needs_nickname,
    experience: {
      completionCode,
      assignmentId: assignment.id,
      status: assignment.status === "PASSED" ? "COMPLETED" : assignment.status,
      revision: assignment.revision,
      taskVersion: assignment.task_version,
      title: assignment.task_title,
      purpose: assignment.task_purpose,
      shortDescription: journeyNode?.short_description ?? assignment.task_purpose,
      learnerOutcome: assignment.learner_outcome,
      referenceMaterials: assignment.reference_materials,
      estimatedMinutes: assignment.estimated_duration_minutes,
      stageKind: assignment.journey_stage?.stage_kind ?? "TASK",
      stageKey: assignment.journey_stage?.stable_key ?? assignment.stable_task_key,
      stagePosition: (assignment.journey_stage?.position ?? journeyNode?.position ?? 0) + 1,
      currentAssignmentId: action.resource_id,
      currentStagePosition: (action.journey?.nodes.find(node => node.assignment_id === action.resource_id)?.position ?? 0) + 1,
      allowedCommands: assignment.allowed_commands,
      materials: learnerMaterialDestinations(assignment.journey_stage?.stable_key ?? assignment.stable_task_key, assignment.learning_materials.map((material) => ({
        key: material.key,
        title: material.title,
        url: material.url,
        completed: material.completed_at !== null,
      }))),
      draftBody: assignment.draft?.body ?? "",
      completedStages: action.journey?.completed_stages ?? 0,
      totalStages: action.journey?.total_stages ?? 8,
      reviewerDisplayName: assignment.reviewer_display_name,
      latestSubmissionBody: latestSubmission?.body ?? null,
      latestSubmissionVersion: latestSubmission?.version_no ?? null,
      latestSubmissionCreatedAt: latestSubmission?.created_at ?? null,
      latestFeedback: assignment.coaching?.feedback ?? assignment.latest_revision_feedback,
      latestFeedbackAt: assignment.coaching?.finalized_at ?? null,
      pendingReviewAssignmentId: ["SUBMITTED", "IN_REVIEW"].includes(assignment.status) ? assignment.id : null,
      activityRecords,
      reviewFeedback: collectReviewFeedback(activityAssignments.map(({ node, detail }) => ({
        detail, position: node.position + 1, title: node.title,
      }))),
      journeyTasks: (action.journey?.nodes ?? []).map((node) => ({
        assignmentStatus: node.assignment_status,
        isRevising: node.is_revising,
        assignmentId: node.assignment_id,
        position: node.position + 1,
        status: node.status,
        title: node.title,
        shortDescription: node.short_description,
      })),
    },
  };
}
