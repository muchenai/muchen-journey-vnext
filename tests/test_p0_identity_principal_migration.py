import importlib.util
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0021_p0_identity_principal.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "p0_identity_principal_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingOperations:
    def __init__(self):
        self.mutations: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.mutations.append((name, args, kwargs))

        return record


def test_upgrade_backfills_identity_revision_before_enforcing_positive_values(monkeypatch):
    migration = load_migration()
    operations = RecordingOperations()
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    names = [name for name, _, _ in operations.mutations]
    assert names == ["add_column", "execute", "create_check_constraint"]
    statement = operations.mutations[1][1][0]
    assert "SET external_identity_revision = external_identity.revision" in statement
    assert "WHERE identity_session.external_identity_id = external_identity.id" in statement


def test_downgrade_only_removes_the_compatibility_revision_column(monkeypatch):
    migration = load_migration()
    operations = RecordingOperations()
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert [name for name, _, _ in operations.mutations] == [
        "drop_constraint",
        "drop_column",
    ]
