# WP-31 Synchronized Snapshot Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the WP-31 Canary dump and its source facts use one PostgreSQL exported snapshot, so normal concurrent source writes cannot be misclassified as restore corruption.

**Architecture:** A small repository-owned helper opens a read-only serializable transaction, exports its snapshot, atomically publishes the opaque snapshot identifier into a root-only exchange directory, and holds the transaction until the backup script releases it. `pg_dump --snapshot` and `db_facts.py` import that same snapshot using a strictly validated client-side SQL literal; only then is the restored database compared with the snapshot-bound facts. Images are pulled before the snapshot is opened, and snapshot failures expose only stable categories or SHA-256 values rather than identifiers or raw driver output.

**Tech Stack:** Bash, Python 3, SQLAlchemy 2.0.51, Psycopg 3.3.4, PostgreSQL `pg_export_snapshot` / `SET TRANSACTION SNAPSHOT` / `pg_dump --snapshot`, pytest, GitHub Actions.

**Spec:** `D:/muchen_journey/9.6日项目阻塞复盘.md` and failed GitHub Actions Run `34078682912`.

## Global Constraints

- The source database remains exactly `journey_next_cutover_20260810`; the isolated target remains exactly `journey_next_canary_20260901_c72fea5`.
- No secret, token, private key, DSN, IP address, raw user identifier, row value, or content fingerprint may be printed or added to an artifact.
- The current binding remains `0388d3327509af813b0e434ac0e49564b7359d2c` / package Run `34057204591` during this code-fix PR; a fresh package, binding, reviewed tag, and execution authorization are mandatory after merge.
- The Canary remains API/Web only, worker and notifications off, at most eight named Learners, `release_go=false`, and `PRODUCTION_CANARY_UAT` bannered.
- Do not dispatch a workflow or create/delete a database while implementing this plan.
- Use only `ghcr.io/muchenai/muchen-journey-vnext-*` runtime images; do not restore the historical `muchenai2024-creator` namespace.
- Preserve encrypted-backup verification, manifest HMAC verification, candidate runtime binding, target-empty guard, and plaintext cleanup.

---

### Task 1: Synchronize Canary dump and facts on one exported snapshot

**Files:**
- Include: `docs/superpowers/plans/2026-09-07-wp31-synchronized-snapshot-restore.md` (this plan; it is documentation, not an Ops-manifest execution dependency)
- Create: `scripts/wp31_database_snapshot.py`
- Create: `tests/test_wp31_database_snapshot.py`
- Create: `tests/test_wp31_database_snapshot_integration.py`
- Modify: `deploy/production/db_facts.py`
- Modify: `deploy/production/greenfield_canary_backup_restore.sh`
- Modify: `.github/workflows/wp15-wartime-production.yml`
- Modify: `tests/test_wp31_greenfield_canary.py`
- Modify: `config/wp31_greenfield_canary_ops_manifest.json`

**Interfaces:**
- Produces: `validate_snapshot_id(value: str) -> str`, `export_snapshot(connection) -> str`, and `import_snapshot(connection, snapshot_id: str) -> None` in `scripts.wp31_database_snapshot`; import renders the validated identifier as a client-side PostgreSQL string literal and sends no server-side bind parameter.
- Produces: CLI `python wp31_database_snapshot.py --exchange-dir /exchange --timeout-seconds 900`, which atomically publishes mode-0600 `snapshot-id`, waits for regular file `snapshot-release`, never prints the identifier, and rolls back on release or error.
- Consumes: optional `WP31_DATABASE_SNAPSHOT` in `deploy/production/db_facts.py`; it is accepted only with `REQUIRE_READ_ONLY=true` and imported before any facts query.
- Produces: backup failure category `RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT`, with only source/restored SHA-256 values in the preceding diagnostic marker.

- [ ] **Step 1: Write failing unit and contract tests**

Add tests that exercise transaction order and injection rejection with a fake SQLAlchemy connection:

```python
def test_export_and_import_snapshot_transaction_order() -> None:
    exported = FakeConnection(snapshot_id="00000003-0000001B-1")
    assert snapshot.export_snapshot(exported) == "00000003-0000001B-1"
    assert exported.statements == [
        "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE",
        "SHOW transaction_read_only",
        "SELECT pg_export_snapshot()",
    ]

    imported = FakeConnection()
    snapshot.import_snapshot(imported, "00000003-0000001B-1")
    assert imported.statements == [
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "SET TRANSACTION SNAPSHOT '00000003-0000001B-1'",
    ]


@pytest.mark.parametrize("value", ["", "abc", "x'; SELECT 1; --", "00000003/0000001B/1"])
def test_snapshot_id_rejects_non_postgresql_format(value: str) -> None:
    with pytest.raises(snapshot.SnapshotError, match="identifier is invalid"):
        snapshot.validate_snapshot_id(value)
```

Add holder tests that create `snapshot-release` through an injected sleep callback, verify rollback and mode-0600 exchange files, prove `snapshot-id` is absent throughout write/fsync and appears only after atomic publication, and assert captured output does not contain the snapshot identifier. Add a `DATABASE_URL`-gated PostgreSQL integration test which skips only when the URL is absent, rejects any present URL outside the repository's disposable `db-test` / `journey_next_test` boundary, asserts SQLAlchemy 2.0.51 and Psycopg 3.3.4, and proves an imported snapshot cannot see a post-export committed row. Update the existing backup contract test to require all of these strings and orderings:

```python
assert 'docker pull "$API_IMAGE"' in backup
assert backup.index('docker pull "$API_IMAGE"') < backup.index(
    'docker run -d --name "$snapshot_container"'
)
assert "wp31_database_snapshot.py" in backup
assert '--snapshot="$snapshot_id"' in backup
assert '-e WP31_DATABASE_SNAPSHOT="$snapshot_id"' in backup
assert '2>"$snapshot_dump_stderr"' in backup
assert 'fail "SNAPSHOT_PG_DUMP_FAILED"' in backup
assert "RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT" in backup
assert "assert source == restored" not in backup
assert 'cp scripts/wp31_database_snapshot.py "$bundle/wp31_database_snapshot.py"' in workflow
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
D:\anaconda\python.exe -m pytest tests/test_wp31_database_snapshot.py tests/test_wp31_greenfield_canary.py -q -p no:cacheprovider
```

Expected: failure because `scripts.wp31_database_snapshot` and the synchronized-snapshot markers do not exist.

- [ ] **Step 3: Implement the exported-snapshot helper**

Implement strict validation and exact transaction setup:

```python
SNAPSHOT_ID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9A-Fa-f]+$")


def export_snapshot(connection: object) -> str:
    connection.rollback()
    connection.exec_driver_sql(
        "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE"
    )
    if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise SnapshotError("snapshot exporter is not read-only")
    return validate_snapshot_id(
        connection.exec_driver_sql("SELECT pg_export_snapshot()").scalar_one()
    )


def import_snapshot(connection: object, snapshot_id: str) -> None:
    value = validate_snapshot_id(snapshot_id)
    connection.rollback()
    connection.exec_driver_sql(
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )
    connection.exec_driver_sql(f"SET TRANSACTION SNAPSHOT '{value}'")
```

The CLI must resolve and validate a non-symlink exchange directory, create a same-directory pending file exclusively with `os.open(..., O_CREAT | O_EXCL, 0o600)`, write and fsync it before atomically linking it into place as `snapshot-id`, wait no longer than the requested bounded timeout for a non-symlink `snapshot-release`, and emit only `WP31_DATABASE_SNAPSHOT=READY`, `WP31_DATABASE_SNAPSHOT=RELEASED`, or `WP31_DATABASE_SNAPSHOT=FAIL error_type=<class>`.

- [ ] **Step 4: Import the synchronized snapshot in `db_facts.py`**

Before `SHOW transaction_read_only` or any facts query, add:

```python
snapshot_id = os.getenv("WP31_DATABASE_SNAPSHOT", "")
if snapshot_id:
    if os.getenv("REQUIRE_READ_ONLY") != "true":
        raise RuntimeError("snapshot facts require read-only mode")
    try:
        from wp31_database_snapshot import import_snapshot

        import_snapshot(connection, snapshot_id)
    except Exception:
        raise SystemExit("WP31_DATABASE_SNAPSHOT_IMPORT=FAIL") from None
```

Keep the existing output schema exactly unchanged. Snapshot import failure must terminate with only the stable category above; suppress any chained SQLAlchemy/Psycopg exception that could contain the snapshot identifier in its statement parameters.

- [ ] **Step 5: Integrate the helper into backup/restore**

Copy the helper into the owner-only bundle. In the backup script, pre-pull the exact digest-bound DB tool and API images before opening a database snapshot; start a uniquely named detached snapshot-holder container; wait boundedly for `snapshot-id`; run:

```bash
pg pg_dump -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$source_database" --format=custom --compress=9 --no-owner --no-acl \
  --snapshot="$snapshot_id" --file=/backup/canary-source.dump
facts "$source_env" "$source_facts" "$snapshot_id"
release_snapshot
pg pg_restore -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$target_database" --exit-on-error --no-owner --no-acl \
  /backup/canary-source.dump
facts "$target_env" "$facts"
```

The `EXIT` trap must release or force-remove the holder container and delete the pending identifier, `snapshot-id`, `snapshot-release`, captured `pg_dump` stderr, the plaintext dump, and the verification dump. Redirect snapshot-bound `pg_dump` stderr to the owner-only backup directory, never print or copy that raw file, delete it immediately, and fail only with `SNAPSHOT_PG_DUMP_FAILED`. Compare `source-facts.json` and `restored-facts.json` with `cmp -s`; on mismatch print only the two SHA-256 values and fail with `RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT`. Preserve the existing post-compare invariants—migration, non-empty counts, and schema hash length—without a raw Python `assert source == restored`. Do not newly require zero stored notification recipients: Canary notification suppression is enforced by its zero-worker runtime boundary, while the copied production snapshot may legitimately contain inactive or active endpoint records.

- [ ] **Step 6: Refresh the Ops manifest hashes**

Compute SHA-256 for every modified or added execution/test file, replace only the matching `files` entries in `config/wp31_greenfield_canary_ops_manifest.json`, and keep its `application_candidate_sha` unchanged at `0388d3327509af813b0e434ac0e49564b7359d2c` for this fix PR. Keep the documentation plan outside the Ops manifest. Add manifest entries for `scripts/wp31_database_snapshot.py`, `tests/test_wp31_database_snapshot.py`, and `tests/test_wp31_database_snapshot_integration.py`.

- [ ] **Step 7: Run focused and WP-31 regression tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
D:\anaconda\python.exe -m pytest tests/test_wp31_database_snapshot.py tests/test_wp31_database_snapshot_integration.py tests/test_wp31_greenfield_canary.py tests/test_wp31_binding_consumers.py tests/test_wp31_ssh_options.py tests/test_wp31_canary_database_guard.py -q -p no:cacheprovider
D:\anaconda\python.exe -m scripts.wp31_ops_closure --repo . --manifest config/wp31_greenfield_canary_ops_manifest.json
```

Expected locally without `DATABASE_URL`: all non-database pytest cases pass and the integration case is skipped; closure JSON has `status=PASS` and `missing=[]`. Required before merge: repository `make api-test` / PR Fast Gate supplies the disposable `db-test` URL and the integration case passes with pinned SQLAlchemy/Psycopg.

- [ ] **Step 8: Commit the implementation**

```powershell
git add docs/superpowers/plans/2026-09-07-wp31-synchronized-snapshot-restore.md scripts/wp31_database_snapshot.py tests/test_wp31_database_snapshot.py tests/test_wp31_database_snapshot_integration.py deploy/production/db_facts.py deploy/production/greenfield_canary_backup_restore.sh tests/test_wp31_greenfield_canary.py config/wp31_greenfield_canary_ops_manifest.json
git commit -m "fix: harden synchronized snapshot import"
```

The commit must contain no generated credential, local evidence file, private key, authorization payload, or database value.
