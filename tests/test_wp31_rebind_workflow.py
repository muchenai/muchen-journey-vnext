from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/wp31-candidate-rebind.yml"


def test_rebind_workflow_is_successful_package_artifact_driven() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "conclusion == 'success'" in text
    assert "wp31-candidate-binding-${{ github.event.workflow_run.id }}" in text
    assert "actions/download-artifact" in text
    assert "wp31_candidate_binding.py verify" in text
    assert "python3 -m pip install --user" in text
    assert '"Mainline Candidate Gate"' in text


def test_rebind_workflow_uses_unique_main_based_branch_and_pr() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: main" in text
    assert "codex/canary-rebind-${{ github.event.workflow_run.id }}" in text
    assert "git push origin HEAD:$branch" in text
    assert ".github/workflows/wp15-wartime-production.yml" in text
    assert "--force" not in text
    assert "gh pr create" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text


def test_rebind_workflow_does_not_receive_production_secrets() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "VOLCENGINE_" not in text
    assert "WP08_" not in text
    assert "WP15_" not in text
    assert "WP09_" not in text


def test_mainline_skips_candidate_package_for_ops_only_changes() -> None:
    mainline = (WORKFLOW.parent / "mainline.yml").read_text(encoding="utf-8")
    assert "application_changed" in mainline
    assert "git diff-tree" in mainline
    assert "steps.scope.outputs.application_changed == 'true'" in mainline
    assert "Candidate-Operation: ops-only" in mainline
    assert 'subject="$(git log -1 --format=\'%s\' "$GITHUB_SHA")"' in mainline
    assert '"[ops-only] chore(ops): rebind Canary evidence' in WORKFLOW.read_text(encoding="utf-8")
    assert "Candidate-Operation: ops-only" in WORKFLOW.read_text(encoding="utf-8")
    assert "Generate candidate binding handoff" in mainline
    assert "artifacts/wp07-candidate/candidate-binding.json" in mainline


def test_rebind_workflow_stops_duplicate_candidate_package() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "duplicate candidate/package" in text
    assert "WP31_REBIND=STOP" in text
    assert "config/wp31_candidate_binding.json" in text
