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


def test_rebind_workflow_uses_unique_main_based_branch_and_pr() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: main" in text
    assert "codex/canary-rebind-${{ github.event.workflow_run.id }}" in text
    assert "git push origin HEAD:$branch" in text
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
