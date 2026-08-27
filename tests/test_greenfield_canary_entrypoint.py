from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wp15-wartime-production.yml"
CANDIDATE = "1bccbbf1706a8216892f5b9b512b1e27ce784101"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def greenfield_package_job() -> str:
    text = workflow_text()
    start = text.index("  greenfield_package:\n")
    end = text.index("  greenfield_canary:\n", start)
    return text[start:end]


def test_greenfield_package_is_exact_candidate_and_confirmation_bound() -> None:
    job = greenfield_package_job()
    assert f"inputs.candidate == '{CANDIDATE}'" in job
    assert "inputs.confirmation == 'PACKAGE_1BCCBBF_GREENFIELD_CANARY'" in job
    assert "ref: ${{ inputs.candidate }}" in job
    assert "test \"$(git -C candidate rev-parse --verify HEAD)\" = '${{ inputs.candidate }}'" in job


def test_greenfield_package_has_no_production_environment_or_infrastructure_secrets() -> None:
    job = greenfield_package_job()
    assert "environment:" not in job
    assert "VOLCENGINE_" not in job
    assert "WP08_" not in job
    assert "WP15_" not in job
    assert "ssh " not in job
    assert "terraform " not in job


def test_greenfield_package_only_pushes_exact_commit_tags() -> None:
    job = greenfield_package_job()
    assert "make -C candidate candidate-registry-check" in job
    assert job.count("docker push") == 1
    assert 'candidate=\'${{ inputs.candidate }}\'' in job
    assert 'muchen-journey-vnext-$service:$candidate' in job
    assert ":latest" not in job


def test_greenfield_package_rechecks_candidate_and_uploads_digest_evidence() -> None:
    job = greenfield_package_job()
    assert "python3 scripts/wp07_candidate.py preflight" in job
    assert "make -C candidate ci-main" in job
    assert "--platform linux/amd64" in job
    assert "wp31_prepare_amd64_dockerfiles.py" in job
    assert "amd64-build-definition-manifest.json" in job
    assert "python3 scripts/wp07_candidate.py registry" in job
    assert "python3 scripts/wp07_candidate.py verify" in job
    assert "name: wp07-candidate-${{ inputs.candidate }}" in job
    assert "non-self-referential evidence checksums" in job
    assert "if grep -qE '[[:space:]]SHA256SUMS$' SHA256SUMS; then exit 2; fi" in job
    assert "sha256sum -c SHA256SUMS" in job


def test_legacy_wartime_candidate_guard_remains_distinct() -> None:
    text = workflow_text()
    legacy = text[text.index("  operate:\n") :]
    assert "inputs.candidate == 'ff53052847a268d025bceb93c3eab37986d50219'" in legacy
    assert CANDIDATE not in legacy
