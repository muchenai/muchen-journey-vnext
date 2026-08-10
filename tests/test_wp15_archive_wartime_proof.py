import hashlib
import hmac
import json
from pathlib import Path

import pytest

from scripts import wp15_archive_wartime_proof as archive


KEY = "k" * 32
RUN_ID = "31346697068"


def proof(directory: Path) -> None:
    encrypted = b"encrypted-only-backup"
    facts = b'{"migration":"0019_wp30_invitation_control"}\n'
    (directory / "journey-next.dump.enc").write_bytes(encrypted)
    (directory / "source-facts.json").write_bytes(facts)
    (directory / "target-facts.json").write_bytes(facts)
    body = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "candidate_sha": archive.CANDIDATE,
        "source_database": "journey_next_staging",
        "isolated_restore_database": archive.TARGET_DATABASE,
        "migration": archive.MIGRATION,
        "decrypted_backup_sha256": "d" * 64,
        "encrypted_backup_sha256": hashlib.sha256(encrypted).hexdigest(),
        "pii_free_facts_sha256": hashlib.sha256(facts).hexdigest(),
        "backup": "PASS",
        "restore": "PASS",
        "encrypted_artifact_decrypt_verified": True,
        "active_notification_recipients": 0,
        "source_modified": False,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["manifest_hmac_sha256"] = hmac.new(
        KEY.encode(), canonical, hashlib.sha256
    ).hexdigest()
    (directory / "backup-manifest.json").write_text(json.dumps(body))


def test_archive_accepts_exact_encrypted_pii_free_proof(tmp_path: Path) -> None:
    proof(tmp_path)
    result = archive.validate(tmp_path, KEY, RUN_ID)
    assert result["source_target_facts_equal"] is True
    assert result["plaintext_present"] is False


def test_archive_rejects_plaintext_or_tampered_facts(tmp_path: Path) -> None:
    proof(tmp_path)
    (tmp_path / "journey-next.dump").write_bytes(b"plaintext")
    with pytest.raises(archive.ArchiveError, match="plaintext"):
        archive.validate(tmp_path, KEY, RUN_ID)
    (tmp_path / "journey-next.dump").unlink()
    (tmp_path / "target-facts.json").write_bytes(b"different")
    with pytest.raises(archive.ArchiveError, match="facts differ"):
        archive.validate(tmp_path, KEY, RUN_ID)


def test_archive_rejects_manifest_hmac_tamper(tmp_path: Path) -> None:
    proof(tmp_path)
    manifest = json.loads((tmp_path / "backup-manifest.json").read_text())
    manifest["migration"] = "0001_initial"
    (tmp_path / "backup-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(archive.ArchiveError, match="HMAC"):
        archive.validate(tmp_path, KEY, RUN_ID)
