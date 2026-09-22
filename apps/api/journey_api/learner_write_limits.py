"""Shared, database-backed limits for authenticated Learner writes."""

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import create_engine, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from journey_api.auth import Actor
from journey_api.config import get_database_settings, get_settings
from journey_api.errors import ApiError
from journey_api.identity import credential_hash
from journey_api.models import AuthRateLimit

POLICIES = {"draft": ((10, 20), (60, 90)), "submit": ((10, 5), (60, 20))}
SCOPES = tuple(f"learner.write.{kind}.{seconds}" for kind, windows in POLICIES.items()
               for seconds, _limit in windows)
# Auth dependencies already hold a business connection. A separate bounded pool
# prevents all requests waiting for a second connection from the same full pool.
counter_engine = create_engine(
    get_database_settings().database_url, pool_size=2, max_overflow=0,
    pool_timeout=30, pool_pre_ping=True,
)
CounterSession = sessionmaker(bind=counter_engine)


def database_now(counter) -> datetime:
    return counter.scalar(func.clock_timestamp())


def enforce_learner_write_limit(actor: Actor, kind: Literal["draft", "submit"]) -> None:
    subject = credential_hash(
        get_settings().session_secret, "learner-write-limit",
        f"{actor.organization_id}:{actor.id}",
    )
    waits: list[int] = []
    try:
        # This transaction commits even if the subsequent business command fails.
        with CounterSession.begin() as counter:
            now = database_now(counter)
            assert isinstance(now, datetime)
            for seconds, limit in POLICIES[kind]:
                start = datetime.fromtimestamp(
                    math.floor(now.timestamp() / seconds) * seconds, UTC,
                )
                attempts = counter.scalar(
                    insert(AuthRateLimit).values(
                        id=uuid.uuid4(), scope=f"learner.write.{kind}.{seconds}",
                        subject_hash=subject, window_started_at=start, attempts=1,
                    ).on_conflict_do_update(
                        constraint="uq_auth_rate_limit_window",
                        set_={"attempts": func.least(AuthRateLimit.attempts + 1, limit + 1)},
                    ).returning(AuthRateLimit.attempts)
                )
                if attempts is not None and attempts > limit:
                    waits.append(max(1, math.ceil((start + timedelta(seconds=seconds) - now).total_seconds())))
            counter.execute(delete(AuthRateLimit).where(
                AuthRateLimit.subject_hash == subject,
                AuthRateLimit.scope.in_(SCOPES),
                AuthRateLimit.window_started_at < now - timedelta(minutes=10),
            ))
    except SQLAlchemyError as exc:
        raise ApiError(
            503, "WRITE_LIMIT_UNAVAILABLE", "保存与提交保护暂时不可用，请稍后重试。",
            retryable=True,
        ) from exc
    if waits:
        raise ApiError(
            429, "RATE_LIMITED",
            "保存过于频繁，请稍后重试。" if kind == "draft" else "提交过于频繁，请稍后重试。",
            details={"retry_after_seconds": max(waits)}, retryable=True,
        )
