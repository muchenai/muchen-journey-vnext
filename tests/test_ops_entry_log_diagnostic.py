"""The production probe must not export raw log values or execute on import."""
import ast
import json
from pathlib import Path
import re


def classifier():
    source = Path("deploy/exploration-release/inspect.py").read_text(encoding="utf-8")
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "safe_application_errors")
    namespace = {"json": json, "re": re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "probe", "exec"), namespace)
    return namespace["safe_application_errors"]


def test_extracts_error_identifiers_without_private_values():
    private = "private-token-should-never-appear"
    result = classifier()(f'''TypeError: Cannot read properties of undefined
digest: '3941254938'
psycopg.errors.InsufficientPrivilege: permission denied for table notification_endpoints
SQL parameters: {private}
File "/app/apps/api/journey_api/ops_routes.py", line 123
{{"path":"/api/v1/ops/identity-access","status":500,"cookie":"{private}"}}
{{"path":"/api/v1/private/{private}","status":500}}
''')
    assert result["digest_found"]
    assert result["denied_tables"] == ["notification_endpoints"]
    assert result["api_frames"] == [("ops_routes.py", "123")]
    assert result["ops_responses"] == [{"path": "/api/v1/ops/identity-access", "status": 500}]
    assert private not in json.dumps(result)


def test_handles_malformed_and_oversized_logs():
    assert classifier()("x" * (4 * 1024 * 1024 + 1)) == {"status": "LOG_LIMIT_EXCEEDED"}
    result = classifier()('garbled {"path":\n{}\n{"path":"/api/v1/ops/audit","status":200}')
    assert result["ops_responses"] == []
    assert result["digest_found"] is False
