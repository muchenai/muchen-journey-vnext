#!/usr/bin/env python3
"""Validate the one-time, staging-only WP-19 publication Web release."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp19_publication_web_only.json"
WORKFLOW = ROOT / ".github/workflows/wp19-publication-web-only.yml"
DEPLOY_SCRIPT = ROOT / "deploy/production/web_only.sh"
SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(
    r"^ghcr\.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:[0-9a-f]{64}$"
)
EXPECTED_CANDIDATE = "12bc627d4310cdba9eba4c67050dc875994ceb31"
EXPECTED_BASELINE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"
EXPECTED_GATE_RUN = 30872461375
EXPECTED_WEB_DIGEST = (
    "ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@"
    "sha256:21e22f681935f617f4ee29f43cc131d471425357e159c0d1a3ac3631a45cf43c"
)
RUNTIME_COMPATIBILITY_PATHS = (
    "apps/api",
    "apps/worker",
    "contracts",
    "migrations",
    "deploy/staging/compose.yaml",
)


class ContractError(RuntimeError):
    """Raised when the publication Web-only boundary differs."""


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ContractError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    try:
        contract = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError("publication Web-only contract is unreadable") from error
    expected_keys = {
        "schema_version",
        "status",
        "candidate_sha",
        "baseline_runtime_sha",
        "candidate_gate_run_id",
        "web_image",
        "target",
        "public_url",
        "migration_revision",
        "purpose",
    }
    if set(contract) != expected_keys:
        raise ContractError("publication Web-only contract keys differ")
    return contract


def validate_contract(contract: dict[str, object]) -> None:
    if contract["schema_version"] != 1:
        raise ContractError("publication Web-only schema must be 1")
    if contract["status"] != "READY_FOR_DEPLOY_AUTHORIZATION":
        raise ContractError("publication Web-only release is not awaiting authorization")
    candidate = str(contract["candidate_sha"])
    baseline = str(contract["baseline_runtime_sha"])
    if not SHA.fullmatch(candidate) or candidate != EXPECTED_CANDIDATE:
        raise ContractError("publication Web candidate differs")
    if not SHA.fullmatch(baseline) or baseline != EXPECTED_BASELINE:
        raise ContractError("publication runtime baseline differs")
    if contract["candidate_gate_run_id"] != EXPECTED_GATE_RUN:
        raise ContractError("publication candidate gate differs")
    image = str(contract["web_image"])
    if not IMAGE.fullmatch(image) or image != EXPECTED_WEB_DIGEST:
        raise ContractError("publication Web image differs")
    if contract["target"] != "staging":
        raise ContractError("publication Web target must remain staging-only")
    if contract["public_url"] != "https://staging-vnext.muchenai.com":
        raise ContractError("publication Web origin differs")
    if contract["migration_revision"] != "0015_wp19_formal_journey":
        raise ContractError("publication migration baseline differs")


def validate_repository(contract: dict[str, object]) -> None:
    candidate = str(contract["candidate_sha"])
    baseline = str(contract["baseline_runtime_sha"])
    git("merge-base", "--is-ancestor", baseline, candidate)
    git("merge-base", "--is-ancestor", candidate, "HEAD")
    runtime_changes = git(
        "diff",
        "--name-only",
        f"{baseline}..{candidate}",
        "--",
        *RUNTIME_COMPATIBILITY_PATHS,
    )
    if runtime_changes:
        raise ContractError("publication Web candidate changes frozen runtime contracts")

    action_source = git("show", f"{candidate}:apps/web/src/app/actions.ts")
    panel_source = git(
        "show", f"{candidate}:apps/web/src/app/ops/invite-management-panel.tsx"
    )
    required_action_fragments = (
        "export type PublishFormalJourneyActionState = SubmissionActionState",
        "return submissionError(error)",
        'apiRequest("/api/v1/ops/formal-journeys/publish"',
    )
    if any(fragment not in action_source for fragment in required_action_fragments):
        raise ContractError("publication Web candidate lacks explicit API error handling")
    required_panel_fragments = (
        "useActionState(",
        "publishFormalJourney",
        "state.requestId",
        "发布受控内测 V1",
    )
    if any(fragment not in panel_source for fragment in required_panel_fragments):
        raise ContractError("publication Web candidate lacks visible error state")


def validate_dispatch_boundary(
    workflow: str | None = None,
    deploy_script: str | None = None,
) -> None:
    workflow = WORKFLOW.read_text() if workflow is None else workflow
    forbidden = (
        "journey.muchenai.com",
        "/srv/journey-next-production",
        "terraform apply",
        "alembic",
        "seed",
    )
    if any(fragment in workflow.lower() for fragment in forbidden):
        raise ContractError("publication workflow exceeds its staging Web-only boundary")
    required = (
        "workflow_dispatch:",
        "DEPLOY_12BC627_PUBLICATION_WEB_ONLY_STAGING",
        "WP19_PUBLICATION_SSH_INGRESS=CLOSED",
        "deploy/production/web_only.sh",
        "https://staging-vnext.muchenai.com",
        "database:\"UNCHANGED\"",
        "business_facts:\"UNCHANGED\"",
    )
    if any(fragment not in workflow for fragment in required):
        raise ContractError("publication workflow is incomplete")
    deploy_script = DEPLOY_SCRIPT.read_text() if deploy_script is None else deploy_script
    if "WP16_EXPECTED_HOME_MARKER" not in deploy_script:
        raise ContractError("Web-only rollback script lacks the candidate home marker")


def main() -> int:
    contract = load_contract()
    validate_contract(contract)
    validate_repository(contract)
    validate_dispatch_boundary()
    print(
        "WP19_PUBLICATION_WEB_ONLY=PASS"
        f" candidate={contract['candidate_sha']}"
        f" baseline={contract['baseline_runtime_sha']}"
        " target=staging authorization=REQUIRED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
