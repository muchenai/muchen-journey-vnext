#!/usr/bin/env python3
"""Apply or roll back the one-time WP-08 Edge routing repair."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"
PRODUCTION_RELEASE = "8e56e759152efcbf17f4373f2132e02a8762af81"
EDGE_CONTAINER = "journey-next-staging-edge-1"
STAGING_WEB_CONTAINER = "journey-next-staging-web-1"
PRODUCTION_WEB_CONTAINER = "journey-next-production-web-1"
COMPOSE_PROJECT = "journey-next-staging"
EDGE_IMAGE = (
    "ghcr.io/muchenai2024-creator/muchen-journey-vnext-edge@"
    "sha256:b7c239fee65c44ac1dccfa76f88253f87e4d7a8ca27b92e419c86a967ecff171"
)
RELEASE_ROOT = Path("/srv/journey-next-staging/releases")
STATE_ROOT = Path("/run")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
RELEASE_DIRECTORY = re.compile(r"^[0-9a-f]{40}-[1-9][0-9]*$")


class EdgeRepairError(RuntimeError):
    """Raised when the bounded Edge repair cannot be proven safe."""


def _run(
    *command: str,
    cwd: Path | None = None,
    timeout: int = 90,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.stdout.strip()


def _require_real_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise EdgeRepairError(f"{label} must be one regular, unlinked file")


def _state_directory(run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise EdgeRepairError("run ID is invalid")
    state = STATE_ROOT / f"wp08-edge-route-repair-{run_id}"
    if state.parent != STATE_ROOT:
        raise EdgeRepairError("repair state path escaped /run")
    return state


def _validate_caddyfile(text: str, *, repaired: bool) -> None:
    expected_staging = (
        "reverse_proxy journey-next-staging-web-1:3000"
        if repaired
        else "reverse_proxy web:3000"
    )
    required = {
        "admin off",
        "{$STAGING_HOST} {",
        "{$PRODUCTION_HOST} {",
        expected_staging,
        "reverse_proxy production-web:3000",
    }
    lines = {line.strip() for line in text.splitlines()}
    if not required.issubset(lines):
        raise EdgeRepairError("Caddyfile differs from the reviewed route contract")
    proxies = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("reverse_proxy ")
    ]
    if proxies != [expected_staging, "reverse_proxy production-web:3000"]:
        raise EdgeRepairError("Caddyfile contains an unreviewed reverse proxy")
    forbidden = (
        "reverse_proxy web:3000"
        if repaired
        else "reverse_proxy journey-next-staging-web-1:3000"
    )
    if forbidden in lines:
        raise EdgeRepairError("Caddyfile contains both old and repaired staging routes")


def _inspect_one(container: str, *, require_running: bool = True) -> dict[str, object]:
    values = json.loads(_run("docker", "inspect", container))
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise EdgeRepairError("container inspection is ambiguous")
    value = values[0]
    if value.get("Name", "").lstrip("/") != container:
        raise EdgeRepairError("container identity differs")
    if require_running and value.get("State", {}).get("Running") is not True:
        raise EdgeRepairError("required container is not running")
    return value


def _aliases(value: dict[str, object]) -> set[str]:
    settings = value.get("NetworkSettings")
    if not isinstance(settings, dict):
        raise EdgeRepairError("container network settings are missing")
    networks = settings.get("Networks")
    if not isinstance(networks, dict):
        raise EdgeRepairError("container networks are missing")
    aliases: set[str] = set()
    for metadata in networks.values():
        if not isinstance(metadata, dict) or not isinstance(metadata.get("Aliases"), list):
            raise EdgeRepairError("container network aliases are missing")
        for alias in metadata["Aliases"]:
            if not isinstance(alias, str):
                raise EdgeRepairError("container network alias is invalid")
            aliases.add(alias)
    return aliases


def _release_directory(*, require_running: bool = True) -> Path:
    edge = _inspect_one(EDGE_CONTAINER, require_running=require_running)
    config = edge.get("Config")
    if not isinstance(config, dict) or config.get("Image") != EDGE_IMAGE:
        raise EdgeRepairError("Edge image differs from the frozen digest")
    labels = config.get("Labels")
    if not isinstance(labels, dict):
        raise EdgeRepairError("Edge Compose labels are missing")
    if labels.get("com.docker.compose.project") != COMPOSE_PROJECT:
        raise EdgeRepairError("Edge Compose project differs")
    if labels.get("com.docker.compose.service") != "edge":
        raise EdgeRepairError("Edge Compose service differs")
    raw = labels.get("com.docker.compose.project.working_dir")
    if not isinstance(raw, str):
        raise EdgeRepairError("Edge release directory label is missing")
    release = Path(raw)
    if release.parent != RELEASE_ROOT or not RELEASE_DIRECTORY.fullmatch(release.name):
        raise EdgeRepairError("Edge release directory is outside the reviewed root")
    if not release.is_dir() or release.is_symlink() or release.resolve() != release:
        raise EdgeRepairError("Edge release directory is unsafe")
    if not release.name.startswith(f"{CANDIDATE}-"):
        raise EdgeRepairError("Edge release is not the authorized candidate")
    for name in (".deployment.env", "Caddyfile", "compose.yaml"):
        _require_real_file(release / name, name)
    return release


def _web_release(container: str) -> str:
    raw = _run(
        "docker",
        "exec",
        container,
        "node",
        "-e",
        (
            "fetch('http://localhost:3000/health/ready')"
            ".then(async r=>{const b=await r.json();"
            "if(!r.ok||b.status!=='ready')process.exit(1);"
            "process.stdout.write(String(b.release||''))})"
            ".catch(()=>process.exit(1))"
        ),
    )
    if not FULL_SHA.fullmatch(raw):
        raise EdgeRepairError("Web readiness release is invalid")
    return raw


def _preflight(*, require_edge_running: bool = True) -> Path:
    if os.geteuid() != 0:
        raise EdgeRepairError("Edge repair must run as root")
    release = _release_directory(require_running=require_edge_running)
    if _web_release(STAGING_WEB_CONTAINER) != CANDIDATE:
        raise EdgeRepairError("staging Web is not the authorized candidate")
    if _web_release(PRODUCTION_WEB_CONTAINER) != PRODUCTION_RELEASE:
        raise EdgeRepairError("production Web differs from the frozen prestate")
    staging_aliases = _aliases(_inspect_one(STAGING_WEB_CONTAINER))
    production_aliases = _aliases(_inspect_one(PRODUCTION_WEB_CONTAINER))
    if not {"web", STAGING_WEB_CONTAINER}.issubset(staging_aliases):
        raise EdgeRepairError("staging Web aliases differ from inventory")
    if not {"web", "production-web"}.issubset(production_aliases):
        raise EdgeRepairError("production Web aliases differ from inventory")
    return release


def _write_in_place(path: Path, text: str) -> None:
    with path.open("r+", encoding="utf-8") as handle:
        handle.seek(0)
        handle.write(text)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def _validate_with_caddy(path: Path) -> None:
    target = "/tmp/Caddyfile.wp08-edge-route-repair"
    try:
        _run("docker", "cp", str(path), f"{EDGE_CONTAINER}:{target}")
        _run(
            "docker",
            "exec",
            EDGE_CONTAINER,
            "caddy",
            "validate",
            "--config",
            target,
            "--adapter",
            "caddyfile",
        )
    finally:
        subprocess.run(
            ["docker", "exec", EDGE_CONTAINER, "rm", "-f", target],
            check=False,
            capture_output=True,
            text=True,
        )


def _recreate_edge(release: Path) -> None:
    _run(
        "docker",
        "compose",
        "--env-file",
        ".deployment.env",
        "-f",
        "compose.yaml",
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "--pull",
        "never",
        "edge",
        cwd=release,
        timeout=120,
    )
    current = _inspect_one(EDGE_CONTAINER)
    config = current.get("Config")
    if not isinstance(config, dict) or config.get("Image") != EDGE_IMAGE:
        raise EdgeRepairError("recreated Edge does not use the frozen image")


def apply_repair(run_id: str, new_caddyfile: Path) -> None:
    state = _state_directory(run_id)
    if not state.is_dir() or state.is_symlink():
        raise EdgeRepairError("repair state directory is absent or unsafe")
    _require_real_file(new_caddyfile, "new Caddyfile")
    release = _preflight()
    current_path = release / "Caddyfile"
    current = current_path.read_text()
    replacement = new_caddyfile.read_text()
    _validate_caddyfile(current, repaired=False)
    _validate_caddyfile(replacement, repaired=True)
    _validate_with_caddy(new_caddyfile)

    backup = state / "Caddyfile.before"
    if backup.exists() or backup.is_symlink():
        raise EdgeRepairError("repair backup already exists")
    backup.write_text(current)
    backup.chmod(0o600)
    try:
        _write_in_place(current_path, replacement)
        _recreate_edge(release)
        active = _run("docker", "exec", EDGE_CONTAINER, "cat", "/etc/caddy/Caddyfile")
        _validate_caddyfile(active, repaired=True)
    except Exception:
        _write_in_place(current_path, current)
        _recreate_edge(release)
        (state / "ROLLED_BACK").write_text("automatic\n")
        raise
    (state / "APPLIED").write_text("reviewed\n")


def rollback_repair(run_id: str) -> None:
    state = _state_directory(run_id)
    if not state.is_dir() or state.is_symlink():
        raise EdgeRepairError("repair state directory is absent or unsafe")
    release = _preflight(require_edge_running=False)
    backup = state / "Caddyfile.before"
    _require_real_file(backup, "repair backup")
    original = backup.read_text()
    _validate_caddyfile(original, repaired=False)
    current_path = release / "Caddyfile"
    active = current_path.read_text()
    if (state / "ROLLED_BACK").is_file():
        _validate_caddyfile(active, repaired=False)
        return
    try:
        _validate_caddyfile(active, repaired=False)
    except EdgeRepairError:
        pass
    else:
        _recreate_edge(release)
        (state / "ROLLED_BACK").write_text("recovery-after-failed-apply\n")
        return
    _validate_caddyfile(active, repaired=True)
    _write_in_place(current_path, original)
    _recreate_edge(release)
    running = _run("docker", "exec", EDGE_CONTAINER, "cat", "/etc/caddy/Caddyfile")
    _validate_caddyfile(running, repaired=False)
    (state / "ROLLED_BACK").write_text("verification-failed\n")


def finalize_repair(run_id: str) -> None:
    state = _state_directory(run_id)
    if not state.is_dir() or state.is_symlink():
        raise EdgeRepairError("repair state directory is absent or unsafe")
    release = _preflight()
    if not (state / "APPLIED").is_file() or (state / "ROLLED_BACK").exists():
        raise EdgeRepairError("repair was not successfully applied")
    _validate_caddyfile((release / "Caddyfile").read_text(), repaired=True)
    shutil.rmtree(state)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("apply", "rollback", "finalize"))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--new-caddyfile", type=Path)
    args = parser.parse_args()
    if args.candidate != CANDIDATE:
        print("WP08_EDGE_ROUTE_REPAIR_ERROR: candidate differs", file=sys.stderr)
        raise SystemExit(1)
    try:
        if args.command == "apply":
            if args.new_caddyfile is None:
                raise EdgeRepairError("apply requires the reviewed Caddyfile")
            apply_repair(args.run_id, args.new_caddyfile)
        elif args.command == "rollback":
            rollback_repair(args.run_id)
        else:
            finalize_repair(args.run_id)
    except (EdgeRepairError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"WP08_EDGE_ROUTE_REPAIR_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(
        "WP08_EDGE_ROUTE_REPAIR=PASS"
        f" action={args.command} candidate={CANDIDATE}"
    )


if __name__ == "__main__":
    main()
