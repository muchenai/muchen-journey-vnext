import type { TaskReviewFeedback } from "./review-feedback";

export type ProjectExperienceData = {
 completionCode?: {
  status: "LOCKED" | "READY" | "MIGRATED" | "NOT_REQUIRED";
  code: string | null;
  completed?: number;
  total?: number;
  expires_at?: string;
 };
 reviewFeedback?: TaskReviewFeedback[];
 assignmentId: string;
 status: string;
 revision: number;
 taskVersion: number;
 title: string;
 purpose: string;
  shortDescription: string;
 learnerOutcome: string;
 referenceMaterials: string[];
 estimatedMinutes: number;
 stageKind: "DAY_0" | "TREASURE" | "ASSESSMENT" | "TASK";
 stageKey: string;
 stagePosition: number;
 currentAssignmentId?: string;
 currentStagePosition?: number;
 allowedCommands: string[];
 materials: Array<{
  key: string;
  title: string;
  url: string | null;
  completed: boolean;
 }>;
 draftBody: string;
 completedStages: number;
 totalStages: number;
  reviewerDisplayName: string;
  latestSubmissionBody: string | null;
  latestSubmissionVersion: number | null;
  latestSubmissionCreatedAt: string | null;
  latestFeedback: string | null;
  latestFeedbackAt: string | null;
  pendingReviewAssignmentId: string | null;
 activityRecords?: Array<{
  assignmentId: string;
  position: number;
  status: string;
  body: string;
  submittedAt: string;
  feedback: string | null;
  feedbackAt: string | null;
 }>;
 journeyTasks: Array<{
  assignmentStatus?: string;
  isRevising?: boolean;
  assignmentId: string;
  position: number;
  status: "COMPLETED" | "CURRENT" | "LOCKED";
  title: string;
  shortDescription: string;
 }>;
};
