"""Exercise real release scripts and Workflow entrypoints without cloud access.

Only root privileges, the /srv test location and Docker are substituted. The
literal environment parser and child exit handling execute as production code.
"""
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wp15-wartime-production.yml"


def step(name):
    return WORKFLOW.read_text().split("      - name: " + name + "\n", 1)[1].split(
        "      - name:", 1
    )[0]


def test_all_canary_compose_entrypoints_load_literal_release_environment():
    inspect = step("Inspect exact public and remote Canary state")
    automatic = step("Automatic rollback after any deploy identity delivery or inspection failure")
    rollback = (ROOT / "deploy/production/greenfield_canary_rollback.sh").read_text()
    assert "./compose.sh" in inspect
    assert "./rollback.sh" in automatic
    assert "set +e" not in automatic
    assert "./compose.sh" in rollback
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text()
    assert './rollback.sh "$PWD"' in deploy
    assert 'cp deploy/production/greenfield_canary_compose.sh "$bundle/compose.sh"' in WORKFLOW.read_text()


def posix(path):
    return re.sub(r"^([A-Za-z]):", lambda m: "/" + m[1].lower(), str(path).replace("\\", "/"))


@pytest.fixture
def release(tmp_path):
    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash required for release entrypoint tests")
    root = tmp_path / "canary"
    target = root / "releases" / ("a" * 40 + "-123456")
    target.mkdir(parents=True)
    workflow = WORKFLOW.read_text()
    # Resolve bundle source from actual Workflow, not a duplicated import map.
    for filename in ("compose.sh", "rollback.sh", "wp31_exec_env.py"):
        match = re.search(r'cp (\S+) "\$bundle/' + re.escape(filename) + '"', workflow)
        assert match, "Workflow is missing release entrypoint: " + filename
        content = (ROOT / match[1]).read_text().replace(
            "/srv/journey-next-production/canary", posix(root)
        ).replace('[[ "${EUID}" -eq 0 ]] || fail "must run as root"', ": # test user")
        (target / filename).write_bytes(content.encode())
        (target / filename).chmod(0o755)
    (target / ".deployment.env").write_bytes(b"API_IMAGE=bound-api\nWEB_IMAGE=bound-web\n")
    (target / "compose.canary.yaml").write_text("synthetic compose fixture\n")
    (target / "Caddyfile.rollback").write_text("synthetic edge fixture\n")
    (target / "edge.sh").write_bytes(b'#!/usr/bin/env bash\necho EDGE >> "$TEST_TRACE"\nexit "${EDGE_FAIL:-0}"\n')
    (target / "edge.sh").chmod(0o755)
    fake = target / "fake_docker.py"
    fake.write_text('''import os,sys
from pathlib import Path
sys.stdout.reconfigure(newline='\\n')
args=sys.argv[1:]
with Path(os.environ['TEST_TRACE']).open('a') as f: f.write('DOCKER '+ ' '.join(args)+'\\n')
if os.environ.get('API_IMAGE')!='bound-api' or os.environ.get('WEB_IMAGE')!='bound-web':
    print('required variable API_IMAGE is missing a value',file=sys.stderr);sys.exit(42)
if 'down' in args: sys.exit(int(os.environ.get('DOWN_FAIL','0')))
if 'config' in args or '--services' in args:
    print('api');print('web')
    if os.environ.get('EXTRA_WORKER'): print('worker')
if '--quiet' in args and os.environ.get('LEFTOVER'): print('synthetic-container')
sys.exit(int(os.environ.get('PS_FAIL','0')) if 'ps' in args else 0)
''')
    # Portable Docker double: execute the real parser/main, replacing only the
    # external Docker process with an executable Python stub on Windows/Linux.
    driver = target / "driver.py"
    driver.write_text('''import os,sys,subprocess
import wp31_exec_env as entry
real_run=subprocess.run
def docker_run(command,**kwargs):
    assert command[:2]==['docker','compose']
    return real_run([sys.executable,'fake_docker.py',*command[1:]],**kwargs)
entry.subprocess.run=docker_run
def docker_exec(file,command,environment):
    assert file=='docker'
    raise SystemExit(docker_run(command,env=environment).returncode)
entry.os.execvpe=docker_exec
sys.argv=sys.argv[1:]
raise SystemExit(entry.main())
''')
    env = {k: v for k, v in os.environ.items() if k not in ("API_IMAGE", "WEB_IMAGE")}
    env.update(TEST_TRACE=str(target / "trace"), TEST_PYTHON=sys.executable.replace("\\", "/"))
    tools = target / "test-bin"
    tools.mkdir()
    shim = tools / "python3"
    shim.write_bytes(b'#!/usr/bin/env bash\nif [[ "$1" == ./wp31_exec_env.py ]]; then exec "$TEST_PYTHON" ./driver.py "$@"; fi\nexec "$TEST_PYTHON" "$@"\n')
    shim.chmod(0o755)
    prefix = 'export PATH="' + posix(tools) + ':$PATH"; '
    (tools / "ssh").write_bytes(b'#!/usr/bin/env bash\nexec bash -c "${@: -1}"\n')
    (tools / "ssh").chmod(0o755)
    (tools / "curl").write_bytes(b'#!/usr/bin/env bash\nprintf \'%s\\n\' \'{"status":"ready","release":"ff53052847a268d025bceb93c3eab37986d50219"}\'\n')
    (tools / "curl").chmod(0o755)

    def run(command, **overrides):
        return subprocess.run([bash, "-c", prefix + command], cwd=target,
                              env={**env, **overrides}, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15)

    return target, run


def test_inspect_actual_workflow_command_in_fresh_shell(release):
    target, run = release
    inspect = step("Inspect exact public and remote Canary state")
    line = next(x.strip() for x in inspect.splitlines() if x.strip().startswith('ssh '))
    command = line.split('root@"$PUBLIC_IP" ', 1)[1][1:-1]
    # Supply the exact resolved test release; all following commands are real.
    command = command.replace('release=$(readlink -f /srv/journey-next-production/canary/current)',
                              'release="' + posix(target) + '"')
    result = run(command)
    assert result.returncode == 0, result.stderr
    assert "config --services" in (target / "trace").read_text()
    assert "ps --status running --services" in (target / "trace").read_text()
    assert run(command, EXTRA_WORKER="1").returncode != 0
    assert run(command, PS_FAIL="7").returncode != 0


@pytest.mark.parametrize("overrides", [{}, {"DOWN_FAIL": "7"}, {"EDGE_FAIL": "8"}, {"LEFTOVER": "1"}, {"PS_FAIL": "9"}])
def test_rollback_reports_all_outcomes_and_never_deletes_database(release, overrides):
    target, run = release
    result = run('./rollback.sh "' + posix(target) + '"', **overrides)
    trace = (target / "trace").read_text()
    assert "EDGE" in trace and "down" in trace
    assert (result.returncode == 0) == (not overrides), result.stderr
    assert ("WP31_CANARY_ROLLBACK=PASS" in result.stdout) == (not overrides)
    assert "DROP" not in trace and "volume" not in trace
    assert target.is_dir() and (target / ".deployment.env").is_file()


def test_missing_environment_fails_without_false_rollback_success(release):
    target, run = release
    (target / ".deployment.env").unlink()
    result = run('./rollback.sh "' + posix(target) + '"')
    assert result.returncode != 0
    assert "WP31_CANARY_ROLLBACK=PASS" not in result.stdout


def test_wrong_release_path_rejected_before_mutation(release):
    target, run = release
    assert run('./rollback.sh /srv/journey-next-production').returncode != 0
    assert not (target / "trace").exists()


@pytest.mark.parametrize("failure", ["0", "7"])
def test_actual_automatic_rollback_workflow_cannot_mask_failed_stop(release, failure):
    target, run = release
    content = step("Automatic rollback after any deploy identity delivery or inspection failure")
    command = textwrap.dedent(content.split("        run: |\n", 1)[1])
    command = command.replace("${{ steps.deploy.outputs.release }}", posix(target))
    command = command.replace("${{ inputs.candidate }}", "a" * 40)
    command = command.replace("/srv/journey-next-production/canary", posix(target.parent.parent))
    if os.name == "nt":
        # Git Bash cannot apply Linux mode bits to inherited Windows ACLs.
        # CI still executes the real install/chmod operations on Linux.
        command = command.replace('install -d -m 0700 ', 'mkdir -p ')
    result = run(command, DOWN_FAIL=failure, RUNNER_TEMP=posix(target), PUBLIC_IP="synthetic-host", GITHUB_RUN_ID="123456")
    assert (result.returncode == 0) == (failure == "0"), result.stderr
    proof = target.parent.parent / "failures/123456.workflow.json"
    assert proof.exists() == (failure == "0")


def test_missing_environment_reproduces_previous_inspection_failure(release):
    target, run = release
    docker = target / "test-bin/docker"
    docker.write_bytes(b'#!/usr/bin/env bash\nexec "$TEST_PYTHON" ./fake_docker.py "$@"\n')
    docker.chmod(0o755)
    # This was the command at ecfa311c / a10a8ea, in a fresh SSH shell.
    result = run('docker compose -f compose.canary.yaml config --services')
    assert result.returncode == 42
    assert "required variable API_IMAGE is missing a value" in result.stderr
    assert run('./compose.sh -f compose.canary.yaml config --services').returncode == 0


@pytest.mark.parametrize("down_failure", ["0", "7"])
def test_manual_rollback_preserves_current_link_on_failure(release, down_failure):
    target, run = release
    current = target.parent.parent / "current"
    try:
        current.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("native symlink permission unavailable; Linux CI covers this path")
    result = run('./rollback.sh', DOWN_FAIL=down_failure)
    assert (result.returncode == 0) == (down_failure == "0"), result.stderr
    assert current.is_symlink() == (down_failure != "0")
