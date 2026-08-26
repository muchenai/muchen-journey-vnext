from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from scripts.muchen_controlled_release_stage import (
    StageError,
    is_source_path,
    stage_candidate,
    verify_stage,
)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["/usr/bin/git", *arguments], cwd=repo, text=True).strip()


class ControlledReleaseStageTests(unittest.TestCase):
    def test_hash_lock_root_files_are_in_source_scope(self) -> None:
        self.assertTrue(is_source_path(PurePosixPath(".gitattributes")))
        self.assertTrue(is_source_path(PurePosixPath("requirements.lock")))
        self.assertTrue(is_source_path(PurePosixPath("requirements-build.lock")))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["/usr/bin/git", "config", "user.email", "test@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["/usr/bin/git", "config", "user.name", "Test"], cwd=self.repo, check=True
        )
        (self.repo / "apps").mkdir()
        (self.repo / "apps/api.py").write_text("base\n", encoding="utf-8")
        (self.repo / ".gitleaks.toml").write_text("[allowlist]\n", encoding="utf-8")
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["/usr/bin/git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["/usr/bin/git", "commit", "-qm", "base"], cwd=self.repo, check=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inventory(self, entries: list[dict[str, object]], *, unknown: int = 0) -> Path:
        path = self.repo / "inventory.json"
        enriched = []
        for entry in entries:
            item = dict(entry)
            source = self.repo / str(item["path"])
            if source.is_file() and not source.is_symlink():
                content = source.read_bytes()
                item.update(
                    file_type="REGULAR",
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )
            else:
                item.update(
                    file_type="MISSING_OR_NON_REGULAR",
                    sha256=None,
                    size_bytes=None,
                )
            enriched.append(item)
        value = {
            "schema_version": 1,
            "git_head": git(self.repo, "rev-parse", "HEAD"),
            "branch": git(self.repo, "branch", "--show-current"),
            "classification_counts": {
                "RELEASE_REQUIRED": sum(
                    item["classification"] == "RELEASE_REQUIRED" for item in enriched
                ),
                "POST_RELEASE_DEFERRED": sum(
                    item["classification"] == "POST_RELEASE_DEFERRED" for item in enriched
                ),
                "UNKNOWN": unknown,
            },
            "entries": enriched,
        }
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_stages_head_plus_release_overlay_and_excludes_deferred(self) -> None:
        (self.repo / "outputs/old-evidence").mkdir(parents=True)
        (self.repo / "outputs/old-evidence/candidate.json").write_text(
            "tracked evidence must not enter source\n", encoding="utf-8"
        )
        (self.repo / "prototypes/boss-dungeon").mkdir(parents=True)
        (self.repo / "prototypes/boss-dungeon/app.js").write_text(
            "tracked prototype must not enter source\n", encoding="utf-8"
        )
        subprocess.run(
            ["/usr/bin/git", "add", "outputs", "prototypes"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["/usr/bin/git", "commit", "-qm", "tracked deferred baseline"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / "apps/api.py").write_text("release\n", encoding="utf-8")
        (self.repo / "README.md").unlink()
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/release.py").write_text("release\n", encoding="utf-8")
        (self.repo / "scripts/deferred.py").write_text("deferred\n", encoding="utf-8")
        inventory = self.inventory(
            [
                {"path": "apps/api.py", "git_status": " M", "classification": "RELEASE_REQUIRED"},
                {"path": "README.md", "git_status": " D", "classification": "RELEASE_REQUIRED"},
                {"path": "scripts/release.py", "git_status": "??", "classification": "RELEASE_REQUIRED"},
                {"path": "scripts/deferred.py", "git_status": "??", "classification": "POST_RELEASE_DEFERRED"},
            ]
        )
        output = self.root / "candidate"
        manifest = stage_candidate(self.repo, inventory, output, "test-stage")
        self.assertEqual((output / "source/apps/api.py").read_text(), "release\n")
        self.assertFalse((output / "source/README.md").exists())
        self.assertEqual((output / "source/scripts/release.py").read_text(), "release\n")
        self.assertEqual((output / "source/.gitleaks.toml").read_text(), "[allowlist]\n")
        self.assertFalse((output / "source/scripts/deferred.py").exists())
        self.assertFalse((output / "source/outputs").exists())
        self.assertFalse((output / "source/prototypes").exists())
        self.assertEqual(stat.S_IMODE((output / "source/apps").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((output / "source/scripts").stat().st_mode), 0o755)
        self.assertFalse((output / "BUILDING.json").exists())
        self.assertTrue((output / "COMPLETE.json").is_file())
        self.assertEqual(manifest["unknown_count"], 0)
        self.assertFalse(manifest["release_candidate"])
        self.assertIsNone(manifest["candidate_commit_sha"])
        self.assertEqual(manifest["deleted_file_count"], 1)
        self.assertEqual(manifest["deleted_files"][0]["path"], "README.md")
        self.assertEqual(manifest["excluded_baseline_file_count"], 2)
        self.assertEqual(
            {item["path"] for item in manifest["excluded_baseline_files"]},
            {
                "outputs/old-evidence/candidate.json",
                "prototypes/boss-dungeon/app.js",
            },
        )
        self.assertEqual(verify_stage(output)["source_tree_sha256"], manifest["source_tree_sha256"])
        (output / "source/apps/api.py").write_text("drift\n", encoding="utf-8")
        with self.assertRaises(StageError):
            verify_stage(output)
        with self.assertRaises(StageError):
            stage_candidate(self.repo, inventory, output, "test-stage")

    def test_unknown_inventory_fails_closed(self) -> None:
        inventory = self.inventory(
            [{"path": "unknown.txt", "git_status": "??", "classification": "UNKNOWN"}],
            unknown=1,
        )
        with self.assertRaises(StageError):
            stage_candidate(self.repo, inventory, self.root / "candidate", "test-stage")

    def test_worktree_drift_after_inventory_fails_closed(self) -> None:
        (self.repo / "apps/api.py").write_text("release\n", encoding="utf-8")
        inventory = self.inventory(
            [{"path": "apps/api.py", "git_status": " M", "classification": "RELEASE_REQUIRED"}]
        )
        (self.repo / "apps/api.py").write_text("drift-after-inventory\n", encoding="utf-8")
        with self.assertRaisesRegex(StageError, "hash no longer matches"):
            stage_candidate(self.repo, inventory, self.root / "candidate", "test-stage")

    def test_output_inside_repo_is_rejected(self) -> None:
        inventory = self.inventory([])
        with self.assertRaises(StageError):
            stage_candidate(self.repo, inventory, self.repo / "candidate", "test-stage")

    def test_symlink_overlay_is_rejected(self) -> None:
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/release.py").symlink_to(self.repo / "README.md")
        inventory = self.inventory(
            [{"path": "scripts/release.py", "git_status": "??", "classification": "RELEASE_REQUIRED"}]
        )
        with self.assertRaises(StageError):
            stage_candidate(self.repo, inventory, self.root / "candidate", "test-stage")


if __name__ == "__main__":
    unittest.main()
