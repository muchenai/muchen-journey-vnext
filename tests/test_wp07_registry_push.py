from types import SimpleNamespace
import pytest

from scripts.wp07_registry_push import push_image


def test_registry_push_retries_transient_failure_and_reports_each_attempt(capsys):
    results = iter((1, 0))
    calls = []
    sleeps = []

    def runner(command, *, check):
        calls.append((command, check))
        return SimpleNamespace(returncode=next(results))

    used = push_image(
        "worker",
        "ghcr.io/example/worker:immutable",
        attempts=3,
        delay_seconds=2,
        runner=runner,
        sleeper=sleeps.append,
    )

    assert used == 2
    assert len(calls) == 2
    assert sleeps == [2]
    output = capsys.readouterr().out
    assert "component=worker attempt=1/3 result=RETRY" in output
    assert "component=worker attempt=2/3 result=PASS" in output


def test_registry_push_fails_closed_after_exact_bound(capsys):
    calls = []

    def runner(command, *, check):
        calls.append((command, check))
        return SimpleNamespace(returncode=1)

    with pytest.raises(RuntimeError, match="registry push failed for api"):
        push_image(
            "api",
            "ghcr.io/example/api:immutable",
            attempts=3,
            delay_seconds=0,
            runner=runner,
            sleeper=lambda _: None,
        )

    assert len(calls) == 3
    assert "attempt=3/3 result=FAIL retries_exhausted=true" in capsys.readouterr().out


@pytest.mark.parametrize("attempts", (0, 4))
def test_registry_push_rejects_unbounded_attempts(attempts):
    with pytest.raises(ValueError, match="attempts must be between 1 and 3"):
        push_image("web", "ghcr.io/example/web:immutable", attempts=attempts)
