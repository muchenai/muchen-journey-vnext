import pytest
from scripts.canary_app_compatibility import validate_changes, ALLOWED_RUNTIME_CHANGES


def test_reviewed_history_and_text_limit_surface_is_allowed():
    validate_changes(list(ALLOWED_RUNTIME_CHANGES))


def test_reviewed_history_and_text_limit_files_are_explicitly_allowed():
    validate_changes([
        "apps/api/journey_api/review_routes.py",
        "apps/api/journey_api/schemas.py",
        "apps/web/scripts/canary-invite-action.test.mjs",
        "apps/web/scripts/resilience-a11y-contract.test.mjs",
        "apps/web/scripts/reviewer-ops-contract.test.mjs",
        "apps/web/scripts/submission-feedback-contract.test.mjs",
        "apps/web/src/app/actions.ts",
        "apps/web/src/app/app/tasks/[assignmentId]/submission-composer.tsx",
        "apps/web/src/app/character-progress.tsx",
        "apps/web/src/app/globals.css",
        "apps/web/src/app/review/[reviewId]/page.tsx",
        "apps/web/src/app/review/[reviewId]/review-workbench.tsx",
        "apps/web/src/app/review/page.tsx",
        "apps/web/src/lib/server/api.ts",
        "apps/web/src/lib/text-length.ts",
        "contracts/openapi.json",
    ])


@pytest.mark.parametrize("path", ["migrations/versions/new.py", "apps/api/journey_api/models.py",
    "apps/api/journey_api/identity.py", "apps/api/journey_api/auth.py", "apps/api/journey_api/config.py",
    "apps/api/Dockerfile", "apps/web/Dockerfile", "apps/web/package-lock.json", "requirements.lock",
    "config/wp31_candidate_binding.json", "apps/worker/new_job.py",
    "apps/web/src/app/app/page.tsx", "apps/web/src/lib/server/session.ts"])
def test_unreviewed_schema_identity_dependency_or_worker_change_rejected(path):
    with pytest.raises(ValueError):
        validate_changes([path])
