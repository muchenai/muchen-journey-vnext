from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts import wp15_rds_database as module


def exact_database(status: str = "Available") -> dict[str, object]:
    return {
        "DBName": module.DATABASE_NAME,
        "CharacterSetName": module.CHARACTER_SET,
        "Collate": module.COLLATE,
        "CType": module.C_TYPE,
        "Owner": module.OWNER,
        "DBStatus": status,
    }


def test_existing_exact_database_is_safe_and_idempotent() -> None:
    with patch.object(
        module,
        "_request",
        return_value={"Databases": [exact_database()]},
    ) as request:
        assert (
            module.create_and_verify("postgres-12345678", "access", "secret")
            == "EXACT_DATABASE_ALREADY_PRESENT"
        )
    assert request.call_count == 1


def test_create_is_exact_and_waits_for_available() -> None:
    responses = [
        {"Databases": []},
        {},
        {"Databases": [exact_database("Unavailable")]},
        {"Databases": [exact_database()]},
    ]
    with patch.object(module, "_request", side_effect=responses) as request:
        assert (
            module.create_and_verify(
                "postgres-12345678",
                "access",
                "secret",
                sleeper=lambda _: None,
            )
            == "CREATED_AND_VERIFIED"
        )
    assert request.call_args_list[1].args[0] == "CreateDatabase"
    assert request.call_args_list[1].args[1] == {
        "InstanceId": "postgres-12345678",
        "DBName": module.DATABASE_NAME,
        "CharacterSetName": module.CHARACTER_SET,
        "Collate": module.COLLATE,
        "CType": module.C_TYPE,
        "Owner": module.OWNER,
    }


def test_mismatched_existing_database_fails_closed() -> None:
    database = exact_database()
    database["Owner"] = "wrong_owner"
    with patch.object(module, "_request", return_value={"Databases": [database]}):
        with pytest.raises(module.ProductionDatabaseError, match="Owner"):
            module.create_and_verify("postgres-12345678", "access", "secret")


def test_rejects_unbounded_instance_identifier() -> None:
    with pytest.raises(module.ProductionDatabaseError, match="identifier"):
        module.create_and_verify("bad", "access", "secret")


def test_create_allows_only_exact_temporary_restore_database() -> None:
    temporary = exact_database()
    temporary["DBName"] = module.RESTORE_DATABASE_NAME
    with patch.object(module, "_request", return_value={"Databases": [temporary]}) as request:
        assert module.create_and_verify(
            "postgres-12345678",
            "access",
            "secret",
            database_name=module.RESTORE_DATABASE_NAME,
        ) == "EXACT_DATABASE_ALREADY_PRESENT"
    assert request.call_args.args[1]["DBName"] == module.RESTORE_DATABASE_NAME

    with pytest.raises(module.ProductionDatabaseError, match="allowlist"):
        module.create_and_verify(
            "postgres-12345678", "access", "secret", database_name="unreviewed"
        )


def test_create_allows_exact_wartime_cutover_database() -> None:
    database = exact_database()
    database["DBName"] = module.WARTIME_DATABASE_NAME
    with patch.object(module, "_request", return_value={"Databases": [database]}):
        assert module.create_and_verify(
            "postgres-12345678",
            "access",
            "secret",
            database_name=module.WARTIME_DATABASE_NAME,
        ) == "EXACT_DATABASE_ALREADY_PRESENT"
