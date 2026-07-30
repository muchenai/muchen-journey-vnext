import pytest

from scripts.wp12b_pool_diagnostic import DiagnosticError, nearest_rank, validate_target


def test_pool_diagnostic_only_accepts_isolated_postgres_targets():
    validate_target(
        "postgresql+psycopg://journey_next:secret@db-test:5432/journey_next_test"
    )
    with pytest.raises(DiagnosticError, match="refuses"):
        validate_target(
            "postgresql+psycopg://journey_next:secret@postgres.internal:5432/"
            "journey_next_staging"
        )
    with pytest.raises(DiagnosticError, match="PostgreSQL"):
        validate_target("sqlite:///journey_next_test")


def test_pool_diagnostic_uses_nearest_rank_percentiles():
    assert nearest_rank([0.4, 0.1, 0.3, 0.2], 0.50) == 0.2
    assert nearest_rank([0.4, 0.1, 0.3, 0.2], 0.95) == 0.4
