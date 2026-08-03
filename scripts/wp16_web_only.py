from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp16_web_only.json"
SHA = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(
    r"ghcr\.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:[0-9a-f]{64}"
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert contract["status"] == "APPROVED_WEB_ONLY"
    assert contract["targets"] == ["staging", "production"]
    assert isinstance(contract["candidate_gate_run_id"], int)
    assert contract["candidate_gate_run_id"] > 0

    candidate = contract["candidate_sha"]
    parent = contract["candidate_parent"]
    baseline = contract["baseline_runtime_sha"]
    assert all(SHA.fullmatch(value) for value in (candidate, parent, baseline))
    assert IMAGE.fullmatch(contract["web_image"])

    assert git("rev-parse", f"{candidate}^") == parent
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    changed = git("diff", "--name-only", f"{parent}..{candidate}").splitlines()
    assert changed and all(path.startswith("apps/web/") for path in changed)
    runtime_changes = git(
        "diff",
        "--name-only",
        f"{baseline}..{candidate}",
        "--",
        "apps/api",
        "apps/worker",
        "contracts",
        "migrations",
    )
    assert runtime_changes == ""
    print(
        "WP16_WEB_ONLY=PASS "
        f"candidate={candidate} baseline={baseline} targets=staging,production"
    )


if __name__ == "__main__":
    main()
