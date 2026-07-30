from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from journey_api.config import get_database_settings


class Base(DeclarativeBase):
    pass


database_settings = get_database_settings()
engine = create_engine(
    database_settings.database_url,
    pool_pre_ping=True,
    pool_size=database_settings.db_pool_size,
    max_overflow=database_settings.db_max_overflow,
    pool_timeout=database_settings.db_pool_timeout_seconds,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session]:
    with SessionLocal() as session:
        yield session
