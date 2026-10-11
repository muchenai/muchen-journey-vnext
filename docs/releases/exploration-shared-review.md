# Exploration internal test shared review

The owner requested that new learner submissions enter a common queue for the existing reviewers except Xu Hanwen (许瀚文). Ordinary Feishu members are not granted reviewer access. Production UUIDs must be resolved from verified staff records; names never form the authorization check.

Configuration (server only):

- `FEISHU_LEARNER_SHARED_REVIEWER_IDS`: comma-separated existing reviewer UUIDs. Empty keeps the prior assigned-review behavior.
- `FEISHU_LEARNER_ORGANIZATION_ID`: the exact existing organization.
- `FEISHU_LEARNER_REVIEWER_ID`: one valid member of the pool, retained as the enrollment's durable lineage owner. All configured pool members may execute shared reviews; the actual executor is recorded separately.
- `REVIEWER_EXCLUDED_USER_IDS`: exact UUIDs denied Reviewer access, including existing sessions and future OAuth callbacks. Other roles and historical records remain intact.

Only new Feishu-created enrollments with durable `review_assignment_mode=SHARED` opt into the pool. Migration 0032 preserves all existing enrollment assignments as `ASSIGNED`; audit log retention cannot change review permissions. Pool members still require an active Reviewer role and same-organization scope. Shared access applies to queue, detail, history and fixed-version attachments. It does not grant Operator or Content Editor rights.

Existing row locking, expected revisions and unique evaluation constraints prevent two concurrent final decisions. Each decision records the actual reviewer in `executor_id` and `created_by`; fixed ownership is not rewritten. Disabling the pool restores assigned visibility without rewriting old audit or evaluation records.

Validation covers shared review completion, recorded executor, excluded OAuth and existing-session access, learner access retention, old and cross-organization isolation, concurrent finalization, and disabling shared mode. Deployment must use a newly built candidate containing this change; candidate `05e7e0d` predates this request.
