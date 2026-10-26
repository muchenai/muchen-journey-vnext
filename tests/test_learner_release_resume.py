"""Exercise PostgreSQL fingerprints and fail-closed resumption boundaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from journey_api.db import engine

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'deploy/learner-project29' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load('facts_guard')
resume = load('resume')


def test_real_postgres_fingerprint_ignores_only_added_phone_column():
    # Temporary tables are connection-local; no application records are changed.
    with engine.connect() as connection:
        connection.execute(text('CREATE TEMP TABLE external_identities (id integer, subject text) ON COMMIT DROP'))
        connection.execute(text("INSERT INTO external_identities VALUES (1, 'first'), (2, 'second')"))
        before = tuple(connection.execute(guard.fingerprint_query('external_identities')).one())
        connection.execute(text("ALTER TABLE external_identities ADD COLUMN phone_ciphertext text NOT NULL DEFAULT ''"))
        connection.execute(text("UPDATE external_identities SET phone_ciphertext='encrypted-test'"))
        assert tuple(connection.execute(guard.fingerprint_query('external_identities')).one()) == before
        connection.execute(text("UPDATE external_identities SET subject='changed' WHERE id=1"))
        assert tuple(connection.execute(guard.fingerprint_query('external_identities')).one()) != before
        connection.rollback()


def test_regular_table_fingerprint_detects_writes_and_empty_table():
    with engine.connect() as connection:
        connection.execute(text('CREATE TEMP TABLE release_probe (id integer, value text) ON COMMIT DROP'))
        empty = tuple(connection.execute(guard.fingerprint_query('release_probe')).one())
        assert empty[0] == 0
        connection.execute(text("INSERT INTO release_probe VALUES (1, 'test')"))
        assert tuple(connection.execute(guard.fingerprint_query('release_probe')).one()) != empty
        connection.rollback()


def state():
    original = {'candidate': resume.CANDIDATE, 'package_run_id': '40306326918',
        'migrations': {'from': '0044_task_author_review', 'to': '0047_learner_notification_reads'},
        'images': {'api': 'sha256:'+'a'*64, 'web': 'sha256:'+'b'*64}, 'old_images': {}}
    old = {'api': 'sha256:'+'c'*64, 'web': 'sha256:'+'d'*64}
    prepared = json.loads(json.dumps(original))
    prepared['old_images'] = old
    prepared['images']['api'] = 'sha256:'+'e'*64
    return prepared, original, old


def test_resume_accepts_only_verified_prepared_manifest():
    resume.validate_state(*state(), activated=False)


@pytest.mark.parametrize('change', ['activated', 'model', 'base', 'schema', 'image', 'candidate', 'package_run'])
def test_resume_rejects_changed_application_or_post_activation_state(change):
    prepared, original, old = state()
    if change == 'model': prepared['unexpected'] = 'override'
    if change == 'base': prepared['old_images'] = {'api': 'other'}
    if change == 'schema': prepared['migrations']['to'] = 'other'
    if change == 'image': prepared['images']['web'] = 'latest'
    if change == 'candidate': original['candidate'] = 'f'*40
    if change == 'package_run': original['package_run_id'] = '1'
    with pytest.raises(AssertionError):
        resume.validate_state(prepared, original, old, change == 'activated')


def test_source_allowlist_and_content_are_verified(tmp_path):
    root = tmp_path.resolve()
    hashes = {}
    for name in resume.SOURCE_FILES:
        (root / name).write_bytes(name.encode())
        hashes[name] = hashlib.sha256(name.encode()).hexdigest()
    resume.verify_source_files(root, hashes)
    with pytest.raises(AssertionError): resume.verify_source_files(root, {**hashes, '../extra': 'a'*64})
    (root / 'facts_guard.py').write_bytes(b'changed')
    with pytest.raises(AssertionError): resume.verify_source_files(root, hashes)


def test_failed_backup_evidence_must_match_and_remain_pre_migration(tmp_path):
    root = tmp_path.resolve()
    raw = json.dumps({'migration': '0044_task_author_review', 'facts': 'same'}).encode()
    for name in ('before.json', 'restored.json'): (root / name).write_bytes(raw)
    read = lambda path: path.read_bytes()
    resume.verify_stopped_backup(root, read)
    (root / 'restored.json').write_text('{}')
    with pytest.raises(AssertionError): resume.verify_stopped_backup(root, read)
    (root / 'restored.json').write_bytes(raw)
    (root / 'backup-receipt.json').write_text('{}')
    with pytest.raises(AssertionError): resume.verify_stopped_backup(root, read)


def test_rehearsal_mismatch_prevents_receipt():
    module = Mock()
    module.Activation = object
    module.SOURCE_SCHEMA = '0044_task_author_review'
    module.TARGET_SCHEMA = '0047_learner_notification_reads'
    def require(value, code):
        if not value: raise AssertionError(code)
    module.require = require
    module.run.side_effect = [b'{"count":1}', b'0044_task_author_review', b'', b'{"count":2}']
    app = resume.resume_type(module, 'fixed guard')()
    app.images = {'api': 'pinned'}
    app.backup = Path('/backup')
    with pytest.raises(AssertionError, match='RESTORE_MIGRATION_CHANGED_BUSINESS_FACTS'):
        app.validate_restored_database('isolated', Path('/restore.env'))
    module.write_new.assert_not_called()
