from journey_api.main import app


def test_legacy_formal_admission_mutations_are_absent_from_public_openapi() -> None:
    document = app.openapi()
    paths = document["paths"]

    assert "/api/v1/ops/enrollments/{enrollment_id}/formal-admission" not in paths
    assert (
        "/api/v1/ops/enrollments/{enrollment_id}/formal-admission/preview"
        not in paths
    )


def test_result_exposes_only_next_training_stage_semantics() -> None:
    result = app.openapi()["components"]["schemas"]["ResultOut"]
    properties = result["properties"]

    assert "next_training_stage" in properties
    assert "system_recommendation" not in properties
    assert "operator_admission" not in properties
    serialized = str(app.openapi()["components"]["schemas"])
    assert "ADMIT" not in serialized
    assert "NOT_ADMIT" not in serialized
    assert "READY" in serialized
    assert "DEFER" in serialized
    assert "NOT_READY" in serialized
