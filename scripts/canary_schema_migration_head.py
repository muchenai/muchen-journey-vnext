"""Print the exact Alembic heads without importing application dependencies."""

from __future__ import annotations

import ast
from pathlib import Path


def migration_heads(directory: Path) -> list[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in directory.glob("*.py"):
        values: dict[str, object] = {}
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                values[target.id] = ast.literal_eval(node.value)
        revision = values.get("revision")
        if isinstance(revision, str):
            revisions.add(revision)
        down_revision = values.get("down_revision")
        if isinstance(down_revision, str):
            parents.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            if not all(isinstance(item, str) for item in down_revision):
                raise ValueError(f"invalid down_revision in {path}")
            parents.update(down_revision)
    return sorted(revisions - parents)


if __name__ == "__main__":
    print(",".join(migration_heads(Path("migrations/versions"))))
