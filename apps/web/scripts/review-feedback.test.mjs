import test from "node:test";
import assert from "node:assert/strict";
import { collectReviewFeedback } from "../src/app/project-ui/review-feedback.ts";

const review = (version, overrides = {}) => ({
  version_no: version, review_id: `review-${version}`, review_status: "FINALIZED",
  review_finalized_at: `2026-10-10T0${version}:00:00Z`, decision: "PASS",
  feedback: "完整的审核反馈", rubric_feedback: [], ...overrides,
});
const item = (id, position, versions) => ({ position, title: `关卡 ${position}`,
  detail: { id, submission: { versions }, rubric: { dimensions: [{ dimension_key: "evidence", title: "证据质量" }] } },
});

test("pending resubmission retains previous human feedback, newest first, scoped per assignment", () => {
  const groups = collectReviewFeedback([
    item("a", 1, [review(1, { decision: "REVISION_REQUIRED" }), review(2), review(3, { review_status: "ASSIGNED", decision: null, review_finalized_at: null })]),
    item("b", 2, [review(4)]),
    item("c", 3, [review(5, { review_status: "IN_REVIEW", decision: null })]),
  ]);
  assert.deepEqual(groups.map(group => group.assignmentId), ["b", "a"]);
  assert.deepEqual(groups[1].records.map(record => record.version), [2, 1]);
  assert.equal(groups[1].records[1].decision, "REVISION_REQUIRED");
});

test("long multiline comments and every dimension comment are preserved without truncation", () => {
  const comment = "长评论段落\n".repeat(250) + "最后一段";
  const groups = collectReviewFeedback([item("a", 1, [review(1, {
    feedback: comment, rubric_feedback: [{ dimension_key: "evidence", rating: "MEETS", score: 8, feedback: "可核查\n有依据" }],
  })])]);
  assert.equal(groups[0].records[0].comment, comment);
  assert.deepEqual(groups[0].records[0].dimensions, [{ title: "证据质量", rating: "MEETS", score: 8, comment: "可核查\n有依据" }]);
});

test("unfinalized, superseded, and missing review facts never become human feedback", () => {
  assert.deepEqual(collectReviewFeedback([item("a", 1, [
    review(1, { review_id: null }), review(2, { review_status: "SUPERSEDED" }),
    review(3, { review_finalized_at: null }), review(4, { decision: null }),
  ])]), []);
});
