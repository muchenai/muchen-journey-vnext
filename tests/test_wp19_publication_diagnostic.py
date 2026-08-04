from scripts import wp19_publication_diagnostic as diagnostic


def line(timestamp: str, body: str) -> str:
    return f"{timestamp} {body}"


def test_classifies_failed_publication_without_returning_raw_log_text():
    result = diagnostic.classify_logs(
        {
            "api": [
                line(
                    "2026-08-04T01:28:27.900000000Z",
                    'INFO: 127.0.0.1 - "POST /api/v1/ops/formal-journeys/publish HTTP/1.1" 500 Internal Server Error',
                ),
                line(
                    "2026-08-04T01:28:27.901000000Z",
                    'psycopg.errors.InsufficientPrivilege: permission denied for table journey_versions',
                ),
                line(
                    "2026-08-04T01:28:27.902000000Z",
                    'File "/app/apps/api/journey_api/journey_service.py", line 121, in publish_catalog_journey',
                ),
            ],
            "web": [
                line(
                    "2026-08-04T01:28:27.938000000Z",
                    "Error: An unexpected response was received from the server.",
                )
            ],
        }
    )

    assert result["publication_attempt_count"] == 1
    assert result["http_statuses"] == [500]
    assert result["exception_classes"] == ["InsufficientPrivilege"]
    assert result["classifiers"] == [
        "insufficient_privilege",
        "internal_server_error",
        "permission_denied",
        "server_action_unexpected_response",
    ]
    assert result["database_objects"] == ["journey_versions"]
    assert result["app_frames"] == ["journey_service.py:121"]
    serialized = str(result)
    assert "127.0.0.1" not in serialized
    assert "publish_catalog_journey" not in serialized


def test_rejects_window_without_failed_publication():
    try:
        diagnostic.classify_logs(
            {
                "api": [
                    line(
                        "2026-08-04T01:28:27.900000000Z",
                        '{"event":"http.request","status":200}',
                    )
                ],
                "web": [],
            }
        )
    except diagnostic.DiagnosticError as error:
        assert "no formal Journey publication request" in str(error)
    else:
        raise AssertionError("missing publication must fail closed")


def test_rejects_generic_500_without_root_cause_metadata():
    try:
        diagnostic.classify_logs(
            {
                "api": [
                    line(
                        "2026-08-04T01:28:27.900000000Z",
                        'INFO: local - "POST /api/v1/ops/formal-journeys/publish HTTP/1.1" 500 Internal Server Error',
                    )
                ],
                "web": [],
            }
        )
    except diagnostic.DiagnosticError as error:
        assert "no safely classifiable runtime error" in str(error)
    else:
        raise AssertionError("generic 500 must not masquerade as a diagnosis")
