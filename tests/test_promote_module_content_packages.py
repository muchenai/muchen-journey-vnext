import copy
import json
import tempfile
import unittest
from pathlib import Path

from journey_api.construction_module_content import ConstructionModuleContentPackage
from scripts.promote_module_content_packages import promote
from scripts.validate_module_content_candidates import manifest_hash, module_hash


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
            for entry in index["packages"]:
                path = Path(tmp) / Path(entry["path"]).name
                ConstructionModuleContentPackage.model_validate_json(
                    path.read_text(encoding="utf-8")
                )

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

    def test_business_field_change_requires_owner_reapproval(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
            module = candidates["modules"][0]
            module["content_items"][0]["title"] += "（业务变更）"
            module["candidate_sha256"] = module_hash(module)
            candidates["manifest_sha256"] = manifest_hash(candidates)
            candidate_path = Path(tmp) / "candidates.json"
            candidate_path.write_text(
                json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ValueError, "approval evidence points to wrong manifest"
            ):
                promote(candidate_path, APPROVALS, BINDING, Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
