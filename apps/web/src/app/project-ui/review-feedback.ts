import type { Assignment } from "../../lib/server/api";

export type TaskReviewFeedback = {
  assignmentId: string;
  position: number;
  title: string;
  records: Array<{
    id: string;
    version: number;
    reviewedAt: string;
    decision: "PASS" | "REVISION_REQUIRED";
    comment: string;
    dimensions: Array<{ title: string; rating: string; score: number | null; comment: string }>;
  }>;
};

export function collectReviewFeedback(items: Array<{ detail: Assignment; position: number; title: string }>): TaskReviewFeedback[] {
  return items.flatMap(({ detail, position, title }) => {
    const records = (detail.submission?.versions ?? []).flatMap<TaskReviewFeedback["records"][number]>(version => {
      if (version.review_status !== "FINALIZED" || !version.review_id || !version.review_finalized_at
        || (version.decision !== "PASS" && version.decision !== "REVISION_REQUIRED")) return [];
      return [{ id: version.review_id, version: version.version_no,
        reviewedAt: version.review_finalized_at, decision: version.decision,
        comment: version.feedback ?? "",
        dimensions: version.rubric_feedback.map(item => ({
          title: detail.rubric.dimensions.find(dimension => dimension.dimension_key === item.dimension_key)?.title ?? item.dimension_key,
          rating: item.rating, score: item.score, comment: item.feedback,
        })),
      }];
    }).sort((a, b) => Date.parse(b.reviewedAt) - Date.parse(a.reviewedAt) || b.version - a.version);
    return records.length ? [{ assignmentId: detail.id, position, title, records }] : [];
  }).sort((a, b) => Date.parse(b.records[0].reviewedAt) - Date.parse(a.records[0].reviewedAt));
}
