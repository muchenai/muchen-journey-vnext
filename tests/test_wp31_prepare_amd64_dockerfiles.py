import json
import subprocess
from pathlib import Path

import pytest

from scripts import wp31_prepare_amd64_dockerfiles as build


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("service", ["api", "worker", "web"])
def test_transform_preserves_reviewed_architecture_aware_dockerfile(service: str) -> None:
    relative, expected_hash = build.FILES[service]
    source = (ROOT / relative).read_bytes()
    assert build.sha256_bytes(source) == expected_hash
    derived = build.transform(source)
    assert derived == source
    assert b"ARG TARGETARCH" in derived
    assert b"amd64) alpine_arch=x86_64;" in derived
    assert b"arm64) alpine_arch=aarch64;" in derived


def test_transform_fails_closed_on_source_drift() -> None:
    source = (ROOT / "apps/api/Dockerfile").read_bytes().replace(
        b"amd64) alpine_arch=x86_64;", b"amd64) alpine_arch=other;", 1
    )
    with pytest.raises(build.Amd64DockerfileError, match="architecture contract drifted"):
        build.transform(source)


def test_prepare_binds_exact_candidate_and_refuses_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        build,
        "git",
        lambda _root, *arguments: build.CANDIDATE
        if arguments == ("rev-parse", "--verify", "HEAD")
        else "",
    )
    output = tmp_path / "derived"
    result = build.prepare(ROOT, output)
    assert result["application_candidate_sha"] == build.CANDIDATE
    assert result["target_platform"] == "linux/amd64"
    assert result["semantic_change"] is False
    manifest = json.loads((output / "build-definition-manifest.json").read_text())
    assert manifest == result
    with pytest.raises(build.Amd64DockerfileError, match="must not already exist"):
        build.prepare(ROOT, output)


def test_prepare_accepts_explicit_candidate_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = "a" * 40
    monkeypatch.setattr(
        build,
        "git",
        lambda _root, *arguments: candidate
        if arguments == ("rev-parse", "--verify", "HEAD")
        else "",
    )
    result = build.prepare(ROOT, tmp_path / "derived", candidate)
    assert result["application_candidate_sha"] == candidate


def test_cli_fails_closed_for_wrong_candidate_without_traceback(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/wp31_prepare_amd64_dockerfiles.py"),
            "--candidate-root",
            str(wrong),
            "--output",
            str(tmp_path / "output"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "WP31_AMD64_BUILD_DEFINITION=FAIL" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
