"""Grant the production runtime role DML-only access after restore/migration."""

from sqlalchemy import create_engine, text


RUNTIME_ROLE = "journey_next_runtime"
DATABASE = "journey_next_restore_20260803"


def main() -> None:
    engine = create_engine(__import__("os").environ["DATABASE_URL"])
    statements = (
        f"GRANT CONNECT ON DATABASE {DATABASE} TO {RUNTIME_ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {RUNTIME_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {RUNTIME_ROLE}",
    )
    with engine.begin() as connection:
        current = connection.execute(text("SELECT current_database()"))
        if current.scalar_one() != DATABASE:
            raise RuntimeError("production grant runner connected to unexpected database")
        for statement in statements:
            connection.execute(text(statement))
    engine.dispose()


if __name__ == "__main__":
    main()
