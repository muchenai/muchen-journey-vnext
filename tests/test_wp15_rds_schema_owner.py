import pytest

import scripts.wp15_rds_schema_owner as schema_owner


def _result(owner: str) -> dict[str, object]:
    return {
        "Schemas": [
            {
                "DBName": schema_owner.DATABASE_NAME,
                "SchemaName": schema_owner.SCHEMA_NAME,
                "Owner": owner,
            }
        ]
    }


def test_repairs_only_the_exact_public_schema(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    results = iter([_result(schema_owner.EXPECTED_PREVIOUS_OWNER), {}, _result(schema_owner.OWNER)])

    def fake_request(action, body, *_args, **_kwargs):
        calls.append((action, body))
        return next(results)

    monkeypatch.setattr(schema_owner, "_request", fake_request)
    outcome = schema_owner.repair_and_verify(
        "postgres-1bf539167c33", "ak", "sk", sleeper=lambda _seconds: None
    )

    assert outcome == "OWNER_REPAIRED_AND_VERIFIED"
    assert calls[1] == (
        "ModifySchemaOwner",
        {
            "InstanceId": "postgres-1bf539167c33",
            "SchemaInfo": [
                {
                    "DBName": "journey_next_production",
                    "SchemaName": "public",
                    "Owner": "journey_next_migrator",
                }
            ],
        },
    )


def test_rejects_unexpected_existing_owner(monkeypatch):
    monkeypatch.setattr(
        schema_owner,
        "_request",
        lambda *_args, **_kwargs: _result("unexpected_owner"),
    )
    with pytest.raises(schema_owner.ProductionSchemaOwnerError, match="changed unexpectedly"):
        schema_owner.repair_and_verify("postgres-1bf539167c33", "ak", "sk")


def test_already_repaired_owner_is_idempotent(monkeypatch):
    calls: list[str] = []

    def fake_request(action, *_args, **_kwargs):
        calls.append(action)
        return _result(schema_owner.OWNER)

    monkeypatch.setattr(schema_owner, "_request", fake_request)
    assert (
        schema_owner.repair_and_verify("postgres-1bf539167c33", "ak", "sk")
        == "EXACT_OWNER_ALREADY_PRESENT"
    )
    assert calls == ["DescribeSchemas"]
