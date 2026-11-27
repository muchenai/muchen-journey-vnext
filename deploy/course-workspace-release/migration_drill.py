"""Rehearse course workspace and profile upgrades in an isolated populated database."""
import hashlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from facts_guard import snapshot
from grant_runtime import grant_read_access
from journey_api.fixtures import LEARNER_ID, OPERATOR_ID, ORGANIZATION_ID
from scripts.wp06_ops import COURSE_WORKSPACE_TABLES as TABLES

SOURCE = "0060_migrated_ai_ownership"
TARGET = "0063_admin_video_storage"
url = make_url(os.environ["DATABASE_URL"])
if os.environ.get("APP_ENV") != "test" or url.database != "journey_course_workspace_drill_test":
    raise RuntimeError("DISPOSABLE_DATABASE_REQUIRED")
engine = create_engine(url)


def alembic(command, revision):
    subprocess.run(["alembic", command, revision], check=True)


def facts():
    with engine.connect() as conn:
        return snapshot(conn)


alembic("upgrade", SOURCE)
subprocess.run([sys.executable, "-m", "journey_api.seed", "--with-formal-journey"], check=True)
media = b"pre-upgrade media"
params = {
    "org": ORGANIZATION_ID, "issuer": OPERATOR_ID, "learner": LEARNER_ID,
    "material": uuid.uuid4(), "file": uuid.uuid4(), "video": uuid.uuid4(),
    "course": uuid.uuid4(), "size": len(media), "data": media,
    "digest": hashlib.sha256(media).hexdigest(),
}
with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO exploration_materials
            (id, organization_id, uploaded_by, name, kind, mime, size, sha256, content)
        VALUES (:material, :org, :issuer, 'original.pdf', 'file', 'application/pdf', :size, :digest, :data)
    """), params)
    conn.execute(text("""
        INSERT INTO knowledge_files (id, organization_id, created_by, size, complete, metadata_json)
        VALUES (:file, :org, :issuer, :size, true, '{}')
    """), params)
    conn.execute(text("INSERT INTO knowledge_chunks (file_id, position, data) VALUES (:file, 0, :data)"), params)
    conn.execute(text("""
        INSERT INTO academy_videos (id, organization_id, created_by, file_name, mime_type, size, complete, sha256)
        VALUES (:video, :org, :issuer, 'original.mp4', 'video/mp4', :size, true, :digest)
    """), params)
    conn.execute(text("INSERT INTO academy_video_chunks (video_id, position, data) VALUES (:video, 0, :data)"), params)
    conn.execute(text("""
        INSERT INTO academy_courses (id, organization_id, author_id, kind, visibility, review_reason, video_id, revision, content)
        VALUES (:course, :org, :issuer, 'internal', 'published', '', :video, 3, '{"title":"Original course"}')
    """), params)
    conn.execute(text("""
        INSERT INTO academy_learning_records
            (organization_id, user_id, course_id, favorite, seconds, duration, progress, completed)
        VALUES (:org, :learner, :course, true, 72, 120, 60, false)
    """), params)

before = facts()
alembic("upgrade", TARGET)
for attempt in range(2):
    after = facts()
    assert set(after) - set(before) == set(TABLES), "UNEXPECTED_TABLE_DELTA"
    assert {table: after[table] for table in before} == before, "EXISTING_RECORD_CHANGED"
    assert all(after[table][0] == 0 for table in TABLES), "UNEXPECTED_NEW_RECORDS"
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == TARGET
        assert conn.execute(text("""
            SELECT purpose, complete, chunked, content
            FROM exploration_materials WHERE id = :material
        """), params).one() == ("exploration", True, False, media)
        # Check the exact 2 GiB boundary on all widened columns without a 2 GiB fixture.
        for table, key in (("academy_videos", "video"), ("knowledge_files", "file"), ("exploration_materials", "material")):
            assert conn.scalar(text(f'UPDATE {table} SET size = 2147483648 WHERE id=:{key} RETURNING size'), params) == 2147483648
        conn.rollback()
    if attempt == 0:
        alembic("downgrade", SOURCE)
        assert facts() == before, "DOWNGRADE_CHANGED_EXISTING_RECORD"
        alembic("upgrade", TARGET)

with engine.connect() as conn:
    if not conn.scalar(text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='journey_next_runtime')")):
        conn.execute(text("CREATE ROLE journey_next_runtime NOLOGIN"))
    table_names = ", ".join("public." + name for name in TABLES)
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table_names} TO journey_next_runtime"))
    for table in TABLES:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert conn.scalar(text("SELECT has_table_privilege('journey_next_runtime', :table, :privilege)"),
                               {"table": "public." + table, "privilege": privilege})
    conn.rollback()

with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO workspace_courses (id, organization_id, author_id, scope, draft)
        VALUES (:course, :org, :issuer, 'village', '{}')
    """), params)
    conn.execute(text("""
        INSERT INTO course_study_records (course_id, user_id, revision, state)
        VALUES (:course, :learner, 1, '{"reflection":"Original chapter reflection"}')
    """), params)
guard = subprocess.run(["alembic", "downgrade", SOURCE], capture_output=True, text=True)
assert guard.returncode != 0 and "Preserve course learning records" in guard.stderr
with engine.connect() as conn:
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == TARGET
    assert conn.scalar(text("SELECT state->>'reflection' FROM course_study_records WHERE course_id=:course"), params) == "Original chapter reflection"
print("0060 -> 0063: original media and learner records preserved, 2 GiB metadata accepted, nine table grants verified; replay and populated downgrade protection passed.", flush=True)

# Exercise the exact live baseline with a completed grant and a saved chapter reflection.
profile_head = "0064_profile_mall_points"
with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO offline_experience_grants (id, organization_id, user_id, issuer_id, batch, reason, points, xp, content)
        VALUES (:grant_id, :org, :learner, :issuer, 'pre-upgrade training', 'Training completed', 3, 30, '{}')
    """), {**params, "grant_id": uuid.uuid4()})
before_profile = facts()
for attempt in range(2):
    alembic("upgrade", "head")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == profile_head
    after = facts()
    assert after.pop("mall_point_exchanges")[0] == 0
    assert after == before_profile, "PROFILE_UPGRADE_CHANGED_EXISTING_RECORD"
    if attempt == 0:
        alembic("downgrade", TARGET)
        assert facts() == before_profile, "PROFILE_DOWNGRADE_CHANGED_EXISTING_RECORD"

with engine.begin() as conn:
    if not conn.scalar(text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='journey_next_runtime')")):
        conn.execute(text("CREATE ROLE journey_next_runtime NOLOGIN"))
    conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON mall_point_exchanges TO journey_next_runtime"))
    grant_read_access(conn)
    conn.execute(text("""
        INSERT INTO mall_point_exchanges (id, organization_id, user_id, request_key, points, spent_xp)
        VALUES (:exchange_id, :org, :learner, 'isolated-rehearsal', 2, 20)
    """), {**params, "exchange_id": uuid.uuid4()})
populated = facts()
guard = subprocess.run(["alembic", "downgrade", TARGET], capture_output=True, text=True)
assert guard.returncode != 0 and "Cannot downgrade while recorded mall point exchanges exist." in guard.stderr
with engine.connect() as conn:
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == profile_head
assert facts() == populated, "REFUSED_DOWNGRADE_CHANGED_EXISTING_RECORD"
print("0063 -> 0064: all existing business fingerprints preserved, empty ledger replay passed, "
      "runtime ledger access is read-only, populated ledger downgrade refused.", flush=True)
