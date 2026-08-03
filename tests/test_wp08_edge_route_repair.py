from pathlib import Path

import pytest

import scripts.wp08_edge_route_repair as repair


OLD = """{
  admin off
  email {$ACME_EMAIL}
}

{$STAGING_HOST} {
  reverse_proxy web:3000
}

{$PRODUCTION_HOST} {
  reverse_proxy production-web:3000
}
"""

NEW = OLD.replace(
    "reverse_proxy web:3000",
    "reverse_proxy journey-next-staging-web-1:3000",
)


def setup_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    state = tmp_path / "wp08-edge-route-repair-123"
    state.mkdir()
    release = tmp_path / "release"
    release.mkdir()
    current = release / "Caddyfile"
    current.write_text(OLD)
    replacement = state / "Caddyfile.new"
    replacement.write_text(NEW)
    monkeypatch.setattr(repair, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(repair, "_preflight", lambda **_kwargs: release)
    monkeypatch.setattr(repair, "_validate_with_caddy", lambda _path: None)
    monkeypatch.setattr(
        repair,
        "_run",
        lambda *args, **_kwargs: current.read_text()
        if args[:3] == ("docker", "exec", repair.EDGE_CONTAINER)
        else "",
    )
    return state, current, replacement


def test_caddy_contract_replaces_only_the_ambiguous_staging_upstream():
    repair._validate_caddyfile(OLD, repaired=False)
    repair._validate_caddyfile(NEW, repaired=True)

    with pytest.raises(repair.EdgeRepairError, match="unreviewed reverse proxy"):
        repair._validate_caddyfile(
            NEW.replace(
                "reverse_proxy production-web:3000",
                "reverse_proxy production-web:3000\n  reverse_proxy surprise:3000",
            ),
            repaired=True,
        )


def test_apply_rollback_and_finalize_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state, current, replacement = setup_repair(tmp_path, monkeypatch)
    recreates: list[Path] = []
    monkeypatch.setattr(repair, "_recreate_edge", recreates.append)

    repair.apply_repair("123", replacement)
    assert current.read_text() == NEW
    assert (state / "Caddyfile.before").read_text() == OLD
    assert (state / "APPLIED").is_file()
    assert len(recreates) == 1

    repair.rollback_repair("123")
    assert current.read_text() == OLD
    assert (state / "ROLLED_BACK").is_file()
    assert len(recreates) == 2

    with pytest.raises(repair.EdgeRepairError, match="not successfully applied"):
        repair.finalize_repair("123")


def test_apply_automatically_restores_original_when_edge_recreate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state, current, replacement = setup_repair(tmp_path, monkeypatch)
    calls = 0

    def recreate(_release: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic recreate failure")

    monkeypatch.setattr(repair, "_recreate_edge", recreate)

    with pytest.raises(RuntimeError, match="synthetic recreate failure"):
        repair.apply_repair("123", replacement)

    assert calls == 2
    assert current.read_text() == OLD
    assert (state / "ROLLED_BACK").is_file()


def test_rollback_recovers_edge_when_file_was_already_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state, current, _replacement = setup_repair(tmp_path, monkeypatch)
    (state / "Caddyfile.before").write_text(OLD)
    recreates: list[Path] = []
    monkeypatch.setattr(repair, "_recreate_edge", recreates.append)

    repair.rollback_repair("123")

    assert current.read_text() == OLD
    assert len(recreates) == 1
    assert (state / "ROLLED_BACK").read_text() == "recovery-after-failed-apply\n"


def test_finalize_removes_only_successful_repair_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state, current, replacement = setup_repair(tmp_path, monkeypatch)
    monkeypatch.setattr(repair, "_recreate_edge", lambda _release: None)

    repair.apply_repair("123", replacement)
    repair.finalize_repair("123")

    assert current.read_text() == NEW
    assert not state.exists()


def test_candidate_and_run_id_are_exact():
    with pytest.raises(repair.EdgeRepairError, match="run ID"):
        repair._state_directory("../123")
    assert repair.FULL_SHA.fullmatch(repair.CANDIDATE)
    assert repair.FULL_SHA.fullmatch(repair.PRODUCTION_RELEASE)
