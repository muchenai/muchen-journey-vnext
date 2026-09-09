import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import wp31_exec_env


def test_env_values_remain_literal_and_are_never_shell_evaluated(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    value = f"$(touch {marker}) ; ' \" $HOME `uname`"
    env_file = tmp_path / "literal.env"
    env_file.write_bytes(f"LITERAL_VALUE={value}\n".encode())

    result = subprocess.run(
        [
            sys.executable,
            str(Path(wp31_exec_env.__file__)),
            "--env-file",
            str(env_file),
            "--",
            sys.executable,
            "-c",
            "import os,sys; sys.stdout.write(os.environ['LITERAL_VALUE'])",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == value
    assert result.stderr == ""
    assert not marker.exists()


def test_env_files_may_repeat_only_identical_values(tmp_path: Path) -> None:
    first = tmp_path / "first.env"
    second = tmp_path / "second.env"
    first.write_bytes(b"API_IMAGE=bound-image\n")
    second.write_bytes(b"API_IMAGE=different-image\n")

    with pytest.raises(wp31_exec_env.EnvContractError, match="disagree"):
        wp31_exec_env.merge_env_files([first, second])


def test_env_files_accept_identical_repeated_values(tmp_path: Path) -> None:
    first = tmp_path / "first.env"
    second = tmp_path / "second.env"
    first.write_bytes(b"API_IMAGE=bound-image\n")
    second.write_bytes(b"API_IMAGE=bound-image\nWEB_IMAGE=bound-web\n")

    assert wp31_exec_env.merge_env_files([first, second]) == {
        "API_IMAGE": "bound-image",
        "WEB_IMAGE": "bound-web",
    }


def test_cli_set_and_child_exit_code_are_preserved(tmp_path: Path) -> None:
    env_file = tmp_path / "base.env"
    env_file.write_bytes(b"BASE_VALUE=base\n")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(wp31_exec_env.__file__)),
            "--env-file",
            str(env_file),
            "--set",
            "EXPLICIT_VALUE=literal-$;value",
            "--",
            sys.executable,
            "-c",
            (
                "import os,sys; "
                "assert os.environ['BASE_VALUE'] == 'base'; "
                "assert os.environ['EXPLICIT_VALUE'] == 'literal-$;value'; "
                "sys.exit(7)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 7
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "content",
    ["lowercase=value\n", "MISSING_EQUALS\n", "DUPLICATE=one\nDUPLICATE=two\n"],
)
def test_env_file_rejects_invalid_contract(tmp_path: Path, content: str) -> None:
    env_file = tmp_path / "invalid.env"
    env_file.write_bytes(content.encode())

    with pytest.raises(wp31_exec_env.EnvContractError):
        wp31_exec_env.read_env_file(env_file)


def test_env_file_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.env"
    target.write_bytes(b"SAFE=value\n")
    link = tmp_path / "link.env"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(wp31_exec_env.EnvContractError, match="unsafe"):
        wp31_exec_env.read_env_file(link)
