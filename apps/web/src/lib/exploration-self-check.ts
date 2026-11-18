/** Persisted feedback and the submitted answer snapshot for an exploration task. */
export type ExplorationSelfCheckRecord = {
  id: string;
  createdAt: string;
  body: string;
  result: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  commentId: string | null;
  mode: "AI" | "DOCUMENT_AI";
  taskVersionId: string;
  assignmentId: string;
  inputKind?: "text" | "document";
  documentUrl?: string | null;
  commentStatus?: "NOT_REQUIRED" | "PENDING" | "SENT" | "FAILED" | "UNCERTAIN";
  commentMessage?: string;
  errorMessage?: string;
  /** Optional on records created before scored exploration assessments existed. */
  score?: number | null;
  maxScore?: number;
  passed?: boolean | null;
  dimensions?: { id: string; name: string; score: number; maxScore: number; feedback: string }[];
  /** True only after the server persisted completion for this assessment. */
  taskCompleted?: boolean;
};
