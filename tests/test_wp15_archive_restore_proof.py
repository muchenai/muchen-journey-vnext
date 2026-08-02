import hashlib
import hmac
import json
from pathlib import Path

import pytest

import scripts.wp15_archive_restore_proof as archive


def proof(tmp_path: Path, key: str) -> Path:
    encrypted = b"encrypted restore artifact"
    (tmp_path / "journey-next.dump.enc").write_bytes(encrypted)
    facts = b'{"migration":"0014_wp12_data_lifecycle"}\n'
    (tmp_path / "source-facts.json").write_bytes(facts)
    (tmp_path / "target-facts.json").write_bytes(facts)
    manifest = {
        "schema_version": 1,
        "run_id": archive.RUN_ID,
        "candidate_sha": archive.CANDIDATE,
        "source_database": "journey_next_staging",
        "isolated_restore_database": archive.TARGET_DATABASE,
        "migration": "0014_wp12_data_lifecycle",
        "decrypted_backup_sha256": "0" * 64,
        "encrypted_backup_sha256": hashlib.sha256(encrypted).hexdigest(),
        "pii_free_facts_sha256": hashlib.sha256(facts).hexdigest(),
        "backup": "PASS",
        "restore": "PASS",
        "encrypted_artifact_decrypt_verified": True,
        "active_notification_recipients": 0,
        "source_modified": False,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_hmac_sha256"] = hmac.new(
        key.encode(), canonical, hashlib.sha256
    ).hexdigest()
    (tmp_path / "backup-manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_validates_exact_encrypted_restore_proof(tmp_path: Path):
    key = "k" * 32
    result = archive.validate(proof(tmp_path, key), key)
    assert result["target_database"] == archive.TARGET_DATABASE
    assert result["source_target_facts_equal"] is True


def test_rejects_plaintext_or_tampered_artifact(tmp_path: Path):
    key = "k" * 32
    directory = proof(tmp_path, key)
    (directory / "journey-next.dump").write_bytes(b"plaintext")
    with pytest.raises(archive.ArchiveError, match="plaintext"):
        archive.validate(directory, key)
    (directory / "journey-next.dump").unlink()
    (directory / "journey-next.dump.enc").write_bytes(b"tampered")
    with pytest.raises(archive.ArchiveError, match="digest"):
        archive.validate(directory, key)
