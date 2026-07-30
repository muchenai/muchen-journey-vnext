#!/usr/bin/env python3
"""Measure bounded SQLAlchemy pool wait against an isolated PostgreSQL test DB."""

from __future__ import annotations

import concurrent.futures
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


CONCURRENCY = 50
HOLD_SECONDS = 0.25
MEASURED_WAVES = 3
ALLOWED_HOSTS = {"db-test", "localhost", "127.0.0.1", "::1"}


class DiagnosticError(RuntimeError):
    """The diagnostic target or result is unsafe or inconclusive."""


@dataclass(frozen=True)
class Scenario:
    name: str
    pool_size: int
    max_overflow: int


@dataclass(frozen=True)
class Result:
    scenario: str
    pool_size: int
    max_overflow: int
    samples: int
    checkout_wait_p50_seconds: float
    checkout_wait_p95_seconds: float
    checkout_wait_max_seconds: float
    total_p95_seconds: float


SCENARIOS = (
    Scenario("current_default", 5, 10),
    Scenario("bounded_candidate", 20, 5),
)


def validate_target(database_url: str) -> None:
    target = make_url(database_url)
    if target.get_backend_name() != "postgresql":
        raise DiagnosticError("diagnostic requires PostgreSQL")
    if target.host not in ALLOWED_HOSTS or not (target.database or "").endswith("_test"):
        raise DiagnosticError("diagnostic refuses non-loopback or non-test databases")


def nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise DiagnosticError("diagnostic produced no samples")
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def wave(engine) -> list[tuple[float, float]]:
    def one(_: int) -> tuple[float, float]:
        started = time.perf_counter()
        with engine.connect() as connection:
            acquired = time.perf_counter()
            connection.execute(text("SELECT pg_sleep(:hold)"), {"hold": HOLD_SECONDS})
        completed = time.perf_counter()
        return acquired - started, completed - started

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        return list(executor.map(one, range(CONCURRENCY)))


def measure(database_url: str, scenario: Scenario) -> Result:
    engine = create_engine(
        database_url,
        pool_size=scenario.pool_size,
        max_overflow=scenario.max_overflow,
        pool_timeout=2,
        pool_pre_ping=True,
    )
    try:
        wave(engine)  # warm connection creation outside the measured sample
        samples = [item for _ in range(MEASURED_WAVES) for item in wave(engine)]
    finally:
        engine.dispose()
    waits = [item[0] for item in samples]
    totals = [item[1] for item in samples]
    return Result(
        scenario=scenario.name,
        pool_size=scenario.pool_size,
        max_overflow=scenario.max_overflow,
        samples=len(samples),
        checkout_wait_p50_seconds=round(nearest_rank(waits, 0.50), 6),
        checkout_wait_p95_seconds=round(nearest_rank(waits, 0.95), 6),
        checkout_wait_max_seconds=round(max(waits), 6),
        total_p95_seconds=round(nearest_rank(totals, 0.95), 6),
    )


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        validate_target(database_url)
        current, bounded = (measure(database_url, scenario) for scenario in SCENARIOS)
        reduction = 1 - (
            bounded.checkout_wait_p95_seconds / current.checkout_wait_p95_seconds
        )
        payload = {
            "schema_version": 1,
            "scope": "ISOLATED_DB_POOL_DIAGNOSTIC",
            "concurrency": CONCURRENCY,
            "hold_seconds": HOLD_SECONDS,
            "measured_waves": MEASURED_WAVES,
            "scenarios": [asdict(current), asdict(bounded)],
            "checkout_wait_p95_reduction": round(reduction, 6),
            "status": "PASS" if reduction >= 0.40 else "INCONCLUSIVE",
            "database_target_recorded": False,
            "business_data_mutated": False,
        }
        print(json.dumps(payload, sort_keys=True))
        if payload["status"] != "PASS":
            raise DiagnosticError("bounded pool did not materially reduce checkout wait")
        return 0
    except (DiagnosticError, ZeroDivisionError) as error:
        print(f"WP12B_POOL_DIAGNOSTIC_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
