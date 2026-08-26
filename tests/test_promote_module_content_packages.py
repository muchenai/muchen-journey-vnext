import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.promote_module_content_packages import promote


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "config/module-content-candidates.v1.json"
APPROVALS = ROOT / "config/module-content-approval-evidence.v1.json"
BINDING = ROOT / "config/exploration-sheet-version-binding.v1.json"


class PromoteModuleContentPackagesTests(unittest.TestCase):
    def test_promotes_four_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = promote(CANDIDATES, APPROVALS, BINDING, Path(tmp))
            self.assertEqual(index["state"], "G1_CONTENT_BINDING_PASS")
            self.assertEqual(len(index["packages"]), 4)
            self.assertFalse(index["production_release_authorized"])

    def test_candidate_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            approvals = json.loads(APPROVALS.read_text(encoding="utf-8"))
            approvals["approvals"][0]["candidate_sha256"] = "0" * 64
            approval_path = Path(tmp) / "approvals.json"
            approval_path.write_text(json.dumps(approvals, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved candidate hash mismatch"):
                promote(CANDIDATES, approval_path, BINDING, Path(tmp) / "out")

    def test_source_binding_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            binding = json.loads(BINDING.read_text(encoding="utf-8"))
            binding["visible_last_modified"] = "unknown"
            binding["canonical_binding"] += "|tampered=true"
            binding_path = Path(tmp) / "binding.json"
            binding_path.write_text(json.dumps(binding, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "binding hash mismatch"):
                promote(CANDIDATES, APPROVALS, binding_path, Path(tmp) / "out")

    def test_nonapproved_decision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            approvals = json.loads(APPROVALS.read_text(encoding="utf-8"))
            approvals["approvals"][1]["decision"] = "CHANGES_REQUIRED"
            approval_path = Path(tmp) / "approvals.json"
            approval_path.write_text(json.dumps(approvals, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approval missing"):
                promote(CANDIDATES, approval_path, BINDING, Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
