from pathlib import Path

import pytest

import scripts.wp08_failed_release_cleanup as cleanup


def failed_release(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "journey-next-staging"
    releases = root / "releases"
    previous = releases / "previous"
    target = releases / f"{cleanup.CANDIDATE}-{cleanup.FAILED_RUN_ID}"
    previous.mkdir(parents=True)
    target.mkdir()
    (root / "current").symlink_to(previous)
    (root / "PREVIOUS_RELEASE").write_text(f"{previous}\n")
    (root / "DEPLOYED_CANDIDATE").write_text(f"{'0' * 40}\n")
    for name in cleanup.EXPECTED_TOP_LEVEL - {"secrets", ".deployment.env"}:
        (target / name).write_text("reviewed\n")
    (target / ".deployment.env").write_text(
        f"CANDIDATE_COMMIT={cleanup.CANDIDATE}\n"
    )
    secrets = target / "secrets"
    secrets.mkdir()
    for name in cleanup.EXPECTED_SECRET_FILES:
        (secrets / name).write_text("SECRET=redacted\n")
    return root, target


def fake_shred(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = cleanup.subprocess.run
    monkeypatch.setattr(cleanup.shutil, "which", lambda _: "/usr/bin/shred")

    def run(command, *args, **kwargs):
        if command[:3] == ["shred", "-u", "--"]:
            Path(command[3]).unlink()
            return None
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(cleanup.subprocess, "run", run)


def test_cleanup_removes_only_the_exact_unreferenced_failed_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, target = failed_release(tmp_path)
    fake_shred(monkeypatch)
    count = cleanup.cleanup_release(
        cleanup.CANDIDATE,
        cleanup.FAILED_RUN_ID,
        root=root,
        require_root=False,
        working_directories=set(),
    )
    assert count == 7
    assert not target.exists()
    assert (root / "current").resolve() == root / "releases" / "previous"
    assert (root / "DEPLOYED_CANDIDATE").read_text().strip() == "0" * 40


def test_cleanup_rejects_current_or_container_referenced_release(tmp_path: Path):
    root, target = failed_release(tmp_path)
    (root / "current").unlink()
    (root / "current").symlink_to(target)
    with pytest.raises(cleanup.CleanupError, match="current release"):
        cleanup.cleanup_release(
            cleanup.CANDIDATE,
            cleanup.FAILED_RUN_ID,
            root=root,
            require_root=False,
            working_directories=set(),
        )

    (root / "current").unlink()
    (root / "current").symlink_to(root / "releases" / "previous")
    with pytest.raises(cleanup.CleanupError, match="Docker container"):
        cleanup.cleanup_release(
            cleanup.CANDIDATE,
            cleanup.FAILED_RUN_ID,
            root=root,
            require_root=False,
            working_directories={target},
        )


def test_cleanup_rejects_any_other_candidate_or_run(tmp_path: Path):
    root, _ = failed_release(tmp_path)
    with pytest.raises(cleanup.CleanupError, match="one-time contract"):
        cleanup.cleanup_release(
            "1" * 40,
            cleanup.FAILED_RUN_ID,
            root=root,
            require_root=False,
            working_directories=set(),
        )
