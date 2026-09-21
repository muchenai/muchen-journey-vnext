import pytest
from scripts.canary_app_compatibility import validate_changes, ALLOWED_RUNTIME_CHANGES


def test_reviewed_post_completion_retest_surface_is_allowed():
    validate_changes(list(ALLOWED_RUNTIME_CHANGES))


def test_reviewed_post_completion_retest_files_are_explicitly_allowed():
    validate_changes([
        "apps/api/journey_api/identity_routes.py",
        "apps/api/journey_api/journey_service.py",
        "apps/api/journey_api/ops_routes.py",
        "apps/api/journey_api/outcome_routes.py",
        "apps/api/journey_api/routes.py",
        "apps/api/journey_api/schemas.py",
        "apps/api/journey_api/submission_routes.py",
        "apps/web/scripts/p0-learner-flow-repair-contract.test.mjs",
        "apps/web/src/app/app/result/page.tsx",
        "apps/web/src/app/ops/page.tsx",
        "apps/web/src/lib/server/api.ts",
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
