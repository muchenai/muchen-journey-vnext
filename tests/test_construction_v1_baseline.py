from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.muchen_construction_v1_baseline import (
    build_worktree_ledger,
    classify_construction_path,
    validate_construction_package,
)


class ConstructionV1BaselineTests(unittest.TestCase):
    def _init_repo(self, root: Path) -> None:
        subprocess.run(["/usr/bin/git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["/usr/bin/git", "config", "user.email", "test@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["/usr/bin/git", "config", "user.name", "Test"],
            cwd=root,
            check=True,
        )
        (root / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["/usr/bin/git", "add", "base.txt"], cwd=root, check=True)
        subprocess.run(["/usr/bin/git", "commit", "-qm", "base"], cwd=root, check=True)

    def test_dispositions_are_explicit(self) -> None:
        self.assertEqual(
            classify_construction_path(
                "docs/baselines/construction-v1.0/README.md"
            )[0],
            "KEEP",
        )
        self.assertEqual(
            classify_construction_path("apps/api/journey_api/shared_domain.py")[0],
            "ADAPT",
        )
        self.assertEqual(
            classify_construction_path(
                "apps/api/journey_api/certification_domain.py"
            )[0],
            "DROP_FROM_CANDIDATE",
        )
        self.assertEqual(
            classify_construction_path(
                "outputs/audits/minimum-runtime-phase0/README.md"
            )[0],
            "ARCHIVE",
        )
        self.assertEqual(
            classify_construction_path("unexpected-product-rule.txt")[0],
            "OWNER_REVIEW_REQUIRED",
        )

    def test_ledger_lists_each_dirty_file_and_excludes_ignored_files(self) -> None:
        if not Path("/usr/bin/git").is_file():
            self.skipTest("host-only inventory test requires /usr/bin/git")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._init_repo(repo)
            (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
            subprocess.run(
                ["/usr/bin/git", "add", ".gitignore"], cwd=repo, check=True
            )
            subprocess.run(
                ["/usr/bin/git", "commit", "-qm", "ignore"], cwd=repo, check=True
            )
            (repo / "base.txt").write_text("changed\n", encoding="utf-8")
            (repo / "unexpected-product-rule.txt").write_text(
                "new\n", encoding="utf-8"
            )
            (repo / ".env").write_text("SECRET=must-not-read\n", encoding="utf-8")

            manifest = build_worktree_ledger(repo, "fixture-run")
            paths = {entry["path"] for entry in manifest["entries"]}

            self.assertEqual(paths, {"base.txt", "unexpected-product-rule.txt"})
            self.assertEqual(manifest["porcelain_file_entry_count"], 2)
            self.assertFalse(manifest["ignored_files_enumerated"])
            self.assertEqual(
                next(
                    item
                    for item in manifest["entries"]
                    if item["path"] == "base.txt"
                )["sha256"],
                hashlib.sha256(b"changed\n").hexdigest(),
            )

    def test_package_validation_rejects_checksum_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "contract.json").write_text(
                json.dumps({"ok": True}) + "\n", encoding="utf-8"
            )
            (package / "SHA256SUMS").write_text(
                f"{'0' * 64}  contract.json\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_construction_package(package)

    def test_package_validation_rejects_duplicate_requirement_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            machine = package / "05_机器合同"
            machine.mkdir(parents=True)
            requirements = {
                "requirements": [{"id": "GOV-001"}, {"id": "GOV-001"}]
            }
            traceability = {
                "source_to_requirements": {"SRC": ["GOV-001"]},
                "module_to_requirements": {"shared": ["GOV-001"]},
                "conflict_resolutions": [],
            }
            (machine / "requirements.v1.json").write_text(
                json.dumps(requirements), encoding="utf-8"
            )
            (machine / "traceability.v1.json").write_text(
                json.dumps(traceability), encoding="utf-8"
            )
            lines = []
            for path in sorted(machine.glob("*.json")):
                lines.append(
                    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                    f"05_机器合同/{path.name}"
                )
            (package / "SHA256SUMS").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "duplicate requirement id"):
                validate_construction_package(package)

    def test_owner_decision_pack_and_requirement_priority_correction_are_explicit(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        correction = json.loads(
            (
                repo
                / "docs/baselines/Muchen_Journey_Construction_V1_Requirement_Priority_Correction_V1.0.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            correction["p0"],
            {
                "pass": 0,
                "ready_for_human": 9,
                "in_progress": 8,
                "blocked_or_gated": 7,
                "total": 24,
            },
        )
        self.assertEqual(
            correction["p1"]["requirements"],
            {"NV-003": "PARTIAL_RUNTIME", "AIA-003": "GAP_P1"},
        )
        self.assertEqual(correction["p1_development"], "STOPPED")
        self.assertEqual(correction["post_release_deferred_development"], "STOPPED")
        self.assertFalse(correction["candidate_frozen"])
        self.assertFalse(correction["ready_for_uat"])

        pack = (
            repo
            / "docs/baselines/Muchen_Journey_Construction_V1_Owner_Decision_Pack_V1.0.md"
        ).read_text(encoding="utf-8")
        for owner in ("郑田源", "屠元琦", "段超群"):
            self.assertIn(owner, pack)
        self.assertIn("PENDING_OWNER_INPUT", pack)
        self.assertIn("technical checkpoint", pack)
        self.assertIn("candidate_frozen=false", pack)
        self.assertIn("release_authorized=false", pack)


if __name__ == "__main__":
    unittest.main()
