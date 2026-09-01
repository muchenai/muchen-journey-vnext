from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.muchen_controlled_release_inventory import build_inventory, classify_path


class ControlledReleaseWorktreeInventoryTests(unittest.TestCase):
    def test_release_scope_and_deferred_paths_are_explicit(self) -> None:
        self.assertEqual(
            classify_path(".gitattributes")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("apps/web/src/lib/journey-program.ts")[0],
            "RELEASE_REQUIRED",
        )
        self.assertEqual(
            classify_path("apps/api/journey_api/certification_domain.py")[0],
            "POST_RELEASE_DEFERRED",
        )
        self.assertEqual(
            classify_path("apps/api/journey_api/shared_domain.py")[0],
            "RELEASE_REQUIRED",
        )
        self.assertEqual(
            classify_path("apps/api/journey_api/appeal_continuity.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("apps/api/journey_api/construction_module_routes.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("migrations/versions/0024_module_content_package_binding.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("migrations/versions/0025_formal_result_gate.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("migrations/versions/0026_identity_organization_scope.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path(
                "migrations/versions/0027_next_training_stage_independent_review.py"
            )[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("requirements-build.lock")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("requirements.lock")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("tests/test_core_identity_database_gate.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("tests/test_identity_invites.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("tests/test_formal_result_database_gate.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("scripts/wp06_ops.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("tests/test_wp06_ops_script.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("docs/baselines/construction-v1.0/README.md")[:2],
            ("RELEASE_REQUIRED", "EVIDENCE_ONLY"),
        )
        self.assertEqual(
            classify_path(
                "docs/baselines/Muchen_Journey_Construction_V1_Owner_Decision_Pack_V1.0.md"
            )[:2],
            ("RELEASE_REQUIRED", "EVIDENCE_ONLY"),
        )
        self.assertEqual(
            classify_path(
                "docs/baselines/Muchen_Journey_Construction_V1_Requirement_Priority_Correction_V1.0.json"
            )[:2],
            ("RELEASE_REQUIRED", "EVIDENCE_ONLY"),
        )
        self.assertEqual(
            classify_path(
                "outputs/controller-integration/construction-v1.0/implementation-evidence/GOV-002.v3.json"
            )[:2],
            ("RELEASE_REQUIRED", "EVIDENCE_ONLY"),
        )
        self.assertEqual(
            classify_path("apps/web/package-lock.json")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("apps/api/journey_api/routes.py")[:2],
            ("RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE"),
        )
        self.assertEqual(
            classify_path("apps/web/src/app/app/result/page.tsx")[:2],
            ("RELEASE_REQUIRED", "REWORK_REQUIRED"),
        )
        self.assertEqual(
            classify_path("docs/baselines/build-contracts/34_future.md")[0],
            "POST_RELEASE_DEFERRED",
        )
        self.assertEqual(
            classify_path(
                "docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.2.md"
            )[:2],
            ("POST_RELEASE_DEFERRED", "FROZEN_REFERENCE"),
        )
        self.assertEqual(
            classify_path(
                "outputs/muchen_journey_p0_human_retest_20260823/retest.xlsx"
            )[:2],
            ("POST_RELEASE_DEFERRED", "FROZEN_REFERENCE"),
        )
        self.assertEqual(
            classify_path("outputs/launch-war-mode-20260808/content.xlsx")[:2],
            ("POST_RELEASE_DEFERRED", "FROZEN_REFERENCE"),
        )
        self.assertEqual(classify_path("unexpected.txt")[0], "UNKNOWN")

    def test_inventory_is_exclusive_and_does_not_list_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["/usr/bin/git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["/usr/bin/git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["/usr/bin/git", "config", "user.name", "Test"], cwd=repo, check=True
            )
            (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(
                ["/usr/bin/git", "add", ".gitignore", "tracked.txt"], cwd=repo, check=True
            )
            subprocess.run(["/usr/bin/git", "commit", "-qm", "base"], cwd=repo, check=True)
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repo / "unexpected.txt").write_text("new\n", encoding="utf-8")
            (repo / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")
            output = repo / "outputs/controller-integration/2026-09-01-controlled-release/run.json"

            manifest = build_inventory(repo, output, "test-run")
            paths = {entry["path"] for entry in manifest["entries"]}

            self.assertIn("tracked.txt", paths)
            self.assertIn("unexpected.txt", paths)
            self.assertNotIn(".env", paths)
            self.assertFalse(manifest["ignored_files_enumerated"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                build_inventory(repo, output, "test-run")

    def test_outside_controlled_output_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["/usr/bin/git", "init", "-q"], cwd=repo, check=True)
            with self.assertRaises(ValueError):
                build_inventory(repo, repo / "outside.json", "test-run")

    def test_manifest_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["/usr/bin/git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["/usr/bin/git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["/usr/bin/git", "config", "user.name", "Test"], cwd=repo, check=True
            )
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["/usr/bin/git", "add", "base.txt"], cwd=repo, check=True)
            subprocess.run(["/usr/bin/git", "commit", "-qm", "base"], cwd=repo, check=True)
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            output = repo / "outputs/controller-integration/2026-09-01-controlled-release/run.json"
            build_inventory(repo, output, "json-run")
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(parsed["snapshot_id"], "json-run")
            self.assertFalse(parsed["output_self_included"])


if __name__ == "__main__":
    unittest.main()
