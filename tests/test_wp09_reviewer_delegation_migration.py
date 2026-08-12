import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0020_wp09_reviewer_delegation.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "wp09_reviewer_delegation_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScalarResult:
    def __init__(self, value: bool):
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class GuardBind:
    def __init__(self, delegation_exists: bool):
        self.delegation_exists = delegation_exists
        self.queries: list[str] = []

    def execute(self, statement):
        self.queries.append(str(statement))
        return ScalarResult(self.delegation_exists)


class GuardedOperations:
    def __init__(self, delegation_exists: bool):
        self.bind = GuardBind(delegation_exists)
        self.mutations: list[tuple[str, tuple, dict]] = []

    def get_bind(self):
        return self.bind

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.mutations.append((name, args, kwargs))

        return record


def test_downgrade_refuses_to_remove_real_delegation_evidence(monkeypatch):
    migration = load_migration()
    operations = GuardedOperations(delegation_exists=True)
    monkeypatch.setattr(migration, "op", operations)

    with pytest.raises(RuntimeError, match="records exist"):
        migration.downgrade()

    assert operations.mutations == []
    assert "SELECT EXISTS" in operations.bind.queries[0]


def test_upgrade_bounds_immutable_evaluation_backfill(monkeypatch):
    migration = load_migration()
    operations = GuardedOperations(delegation_exists=False)
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    statements = [
        args[0]
        for name, args, _ in operations.mutations
        if name == "execute" and args
    ]
    drop_index = statements.index(
        "DROP TRIGGER trg_reject_evaluation_mutation ON evaluations"
    )
    backfill_index = statements.index("UPDATE evaluations SET executor_id = created_by")
    restore_index = next(
        index
        for index, statement in enumerate(statements)
        if "CREATE TRIGGER trg_reject_evaluation_mutation" in statement
    )
    assert drop_index < backfill_index < restore_index


def test_empty_delegation_table_can_return_to_previous_schema(monkeypatch):
    migration = load_migration()
    operations = GuardedOperations(delegation_exists=False)
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert [name for name, _, _ in operations.mutations] == [
        "drop_constraint",
        "create_check_constraint",
        "drop_index",
        "drop_constraint",
        "drop_column",
        "execute",
        "execute",
        "drop_table",
    ]
    assert operations.mutations[-1][1] == ("review_delegations",)
