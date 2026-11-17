/** Persisted feedback and the submitted answer snapshot for an exploration task. */
export type ExplorationSelfCheckRecord = {
  id: string;
  createdAt: string;
  body: string;
  result: string;
  status: "COMPLETED" | "FAILED";
  commentId: string | null;
  mode: "AI" | "DOCUMENT_AI";
  taskVersionId: string;
  assignmentId: string;
};
