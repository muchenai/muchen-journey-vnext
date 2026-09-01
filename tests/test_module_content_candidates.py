from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_module_content_candidates import validate


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/module-content-candidates.v1.json"


class ModuleContentCandidatesTests(unittest.TestCase):
    def test_current_manifest_passes(self) -> None:
        result = validate(MANIFEST)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["modules"], 4)
        self.assertEqual(result["tasks"], 7)

    def test_tamper_fails_hash_check(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        value["modules"][0]["tasks"][0]["purpose"] += "篡改"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate hash mismatch"):
                validate(path)

    def test_same_primary_and_backup_rejected(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        value["shared_reviewer_policy"]["backup_reviewers"] = ["万雨欣"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-reviewer.json"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "backup reviewer"):
                validate(path)

    def test_machine_cannot_claim_owner_signature(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        value["modules"][1]["owner_hash_signature_state"] = "APPROVED"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "false-signature.json"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "machine must not sign"):
                validate(path)


if __name__ == "__main__":
    unittest.main()
