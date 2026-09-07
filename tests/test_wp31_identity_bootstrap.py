import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts import wp31_identity_bootstrap as bootstrap


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _BootstrapSession:
    def __init__(self, organizations: list[object]) -> None:
        self.organizations = organizations
        self.added: list[object] = []

    def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self.organizations)

    def scalar(self, _statement: object) -> None:
        return None

    def add_all(self, rows: list[object]) -> None:
        self.added.extend(rows)

    def flush(self) -> None:
        return None


def _request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operator_user_id": str(uuid.uuid4()),
        "operator_display_name": "许瀚文",
        "learner_user_id": str(uuid.uuid4()),
        "learner_display_name": "组长",
        "owner_user_id": str(uuid.uuid4()),
        "owner_display_name": "刘默文",
        "authorization_reference": "IDENTITY-BOOTSTRAP-20260904",
        "expires_in_minutes": 15,
    }
    value.update(overrides)
    return value


def test_request_parser_accepts_exact_non_sensitive_shape(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(_request(), ensure_ascii=False) + "\n", encoding="utf-8")

    parsed = bootstrap.parse_request(path)

    assert parsed.operator_display_name == "许瀚文"
    assert parsed.learner_display_name == "组长"
    assert parsed.expires_in_minutes == 15
    assert parsed.operator_user_id.version == 4
    assert parsed.learner_user_id.version == 4


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unexpected", "secret", "fields differ"),
        ("operator_user_id", "not-a-uuid", "UUIDv4"),
        ("operator_display_name", "bad\nname", "display name"),
        ("learner_display_name", "许瀚文", "must differ"),
        ("owner_display_name", "许瀚文", "must differ"),
        ("authorization_reference", "token value", "authorization reference"),
        ("expires_in_minutes", 31, "5-30"),
    ],
)
def test_request_parser_rejects_unsafe_or_ambiguous_input(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    payload = _request()
    payload[field] = value
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError, match=message):
        bootstrap.parse_request(path)


def test_request_parser_rejects_same_user_id() -> None:
    user_id = str(uuid.uuid4())
    with pytest.raises(bootstrap.BootstrapError, match="must differ"):
        bootstrap.parse_payload(_request(learner_user_id=user_id, operator_user_id=user_id))


def test_request_parser_rejects_owner_id_collision() -> None:
    user_id = str(uuid.uuid4())
    with pytest.raises(bootstrap.BootstrapError, match="must differ"):
        bootstrap.parse_payload(_request(owner_user_id=user_id, learner_user_id=user_id))


def test_runtime_guard_allows_only_exact_isolated_canary_and_tls() -> None:
    valid = (
        "postgresql+psycopg://journey_next_migrator:pw@"
        "private.rds.example:5432/journey_next_cutover_20260810"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )
    with pytest.raises(bootstrap.BootstrapError, match="Canary database"):
        bootstrap.validate_runtime(
            valid,
            app_env="production",
            release_marker="PRODUCTION_CANARY_UAT",
            confirmation=bootstrap.CONFIRMATION,
        )

    target = valid.replace("journey_next_cutover_20260810", "journey_next_canary_20260901_c72fea5")
    assert bootstrap.validate_runtime(
        target,
        app_env="production",
        release_marker="PRODUCTION_CANARY_UAT",
        confirmation=bootstrap.CONFIRMATION,
        database_kind="canary",
    ) is None

    target = valid.replace("journey_next_cutover_20260810", "journey_next_canary_20260901_c72fea5")
    for database_url, message in [
        (valid.replace("journey_next_cutover_20260810", "journey_next_dev"), "Canary database"),
        (target.replace("sslmode=verify-full", "sslmode=require"), "verify-full"),
        (target.replace("private.rds.example", "localhost"), "host"),
        (target.replace("journey_next_migrator", "journey_next_runtime"), "credentials"),
        (target.replace("/run/secrets/volcengine-rds-ca.pem", "/tmp/ca.pem"), "CA path"),
    ]:
        with pytest.raises(bootstrap.BootstrapError, match=message):
            bootstrap.validate_runtime(
                database_url,
                app_env="production",
                release_marker="PRODUCTION_CANARY_UAT",
                confirmation=bootstrap.CONFIRMATION,
                database_kind="canary",
            )


def test_public_result_contains_ids_and_link_but_never_display_names() -> None:
    result = bootstrap.public_result(
        {
            "operator_user_id": "operator",
            "learner_user_id": "learner",
            "owner_user_id": "owner",
            "operator_roles": ["OPERATOR", "REVIEWER"],
            "owner_roles": ["LEARNER", "REVIEWER"],
            "operator_link_id": "link",
            "operator_link_start_path": "/auth/feishu?link_token=opaque",
            "operator_link_expires_at": "2026-09-04T12:15:00+00:00",
            "expires_in_minutes": 15,
            "operator_display_name": "许瀚文",
            "learner_display_name": "组长",
            "owner_display_name": "刘默文",
        }
    )

    assert result["operator_user_id"] == "operator"
    assert result["owner_user_id"] == "owner"
    assert result["owner_roles"] == ["LEARNER", "REVIEWER"]
    assert "operator_display_name" not in result
    assert "learner_display_name" not in result
    assert "owner_display_name" not in result
    assert "组长" not in json.dumps(result, ensure_ascii=False)
    assert "刘默文" not in json.dumps(result, ensure_ascii=False)


def test_bootstrap_uses_the_only_non_wp12b_organization_in_the_restored_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import identity as identity_module
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization, User

    business = Organization(id=uuid.uuid4(), name="Muchen Journey")
    run_ids = (
        "30433586481",
        "30482295111",
        "30486354070",
        "30487668744",
        "30508873351",
        "30525165474",
    )
    synthetic = [
        Organization(
            id=uuid.uuid4(),
            name=f"WP12B:wp12b-{run_id}:org-{organization_index:03d}",
        )
        for run_id in run_ids
        for organization_index in range(1, 21)
    ]
    session = _BootstrapSession([business, *synthetic])
    monkeypatch.setattr(identity_module, "add_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wp09_bootstrap,
        "create_operator_link",
        lambda *args, **kwargs: {
            "link_id": "link",
            "start_path": "/auth/feishu?return_to=%2Fops&link_token=opaque",
            "expires_at": "2026-09-07T12:15:00+00:00",
            "expires_in_minutes": 15,
        },
    )

    result = bootstrap.bootstrap(
        session,
        bootstrap.parse_payload(_request()),
        "identity-subject-secret-with-32-bytes",
    )

    users = [row for row in session.added if isinstance(row, User)]
    assert len(users) == 3
    assert {user.organization_id for user in users} == {business.id}
    assert result["operator_link_id"] == "link"


@pytest.mark.parametrize(
    "organization_names",
    [
        ["WP12B:wp12b-30525165474:org-001"],
        ["Business A", "Business B"],
        ["Muchen Journey", "WP12B:manual:org-001"],
        [
            "WP12B:wp12b-30525165474:org-001",
            "WP12B:manual:org-002",
        ],
        [
            "WP12B:wp12b-30525165474:org-001",
            " wp12b:wp12b-30525165474:org-002",
        ],
        [
            "WP12B:wp12b-30525165474:org-001",
            "WP12B：wp12b-30525165474:org-002",
        ],
    ],
)
def test_bootstrap_rejects_ambiguous_non_wp12b_organization_topology(
    monkeypatch: pytest.MonkeyPatch,
    organization_names: list[str],
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api.models import Organization

    session = _BootstrapSession(
        [Organization(id=uuid.uuid4(), name=name) for name in organization_names]
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match="identity bootstrap organization topology is ambiguous",
    ) as captured:
        bootstrap.bootstrap(
            session,
            bootstrap.parse_payload(_request()),
            "identity-subject-secret-with-32-bytes",
        )
    assert captured.value.category == "ORGANIZATION_TOPOLOGY_REJECTED"


def test_bootstrap_converts_operator_link_rejection_to_a_stable_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import identity as identity_module
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization

    session = _BootstrapSession(
        [Organization(id=uuid.uuid4(), name="Muchen Journey")]
    )
    monkeypatch.setattr(identity_module, "add_audit", lambda *args, **kwargs: None)

    def reject_link(*_args: object, **_kwargs: object) -> None:
        raise wp09_bootstrap.BootstrapError("sensitive operator link detail")

    monkeypatch.setattr(wp09_bootstrap, "create_operator_link", reject_link)

    with pytest.raises(
        bootstrap.BootstrapError,
        match="operator link bootstrap was rejected",
    ) as captured:
        bootstrap.bootstrap(
            session,
            bootstrap.parse_payload(_request()),
            "identity-subject-secret-with-32-bytes",
        )
    assert captured.value.category == "OPERATOR_LINK_REJECTED"
    assert "sensitive operator link detail" not in str(captured.value)


def test_cli_reports_a_stable_failure_category_on_stderr_without_reason_details(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root), str(root / "apps" / "api"))),
        "APP_ENV": "production",
        "RELEASE_MARKER": "PRODUCTION_CANARY_UAT",
        "DATABASE_URL": (
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        "SESSION_SECRET": "s" * 32,
        "INVITE_SECRET": "i" * 32,
        "IMPORT_SIGNING_KEY": "k" * 32,
        "IDENTITY_SUBJECT_SECRET": "d" * 32,
        "FEISHU_OAUTH_ENABLED": "true",
        "FEISHU_APP_ID": "test-app",
        "FEISHU_APP_SECRET": "f" * 16,
        "FEISHU_OAUTH_REDIRECT_URI": "https://journey.muchenai.com/auth/feishu/callback",
        "NOTIFICATION_CHANNEL": "FEISHU",
        "NOTIFICATION_RECIPIENTS_ENABLED": "false",
        "ATTACHMENTS_ENABLED": "false",
        "ALLOW_FIXTURE_IDENTITY": "false",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "wp31_identity_bootstrap.py"),
            "--database-kind",
            "canary",
            "--request",
            str(request),
            "--confirm",
            bootstrap.CONFIRMATION,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "WP31_IDENTITY_BOOTSTRAP=FAIL category=BOOTSTRAP_REJECTED\n"
    assert "fields differ" not in result.stderr


def test_main_redacts_unexpected_runtime_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "apps" / "api"))
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(_request(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    config_module = ModuleType("journey_api.config")
    config_module.get_settings = lambda: SimpleNamespace(
        database_url=(
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        app_env="production",
        release_marker="PRODUCTION_CANARY_UAT",
        identity_subject_secret="d" * 32,
    )
    db_module = ModuleType("journey_api.db")

    def fail_session() -> None:
        raise RuntimeError("sensitive database host and SQL parameters")

    db_module.SessionLocal = fail_session
    monkeypatch.setitem(sys.modules, "journey_api.config", config_module)
    monkeypatch.setitem(sys.modules, "journey_api.db", db_module)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "wp31_identity_bootstrap.py",
            "--database-kind",
            "canary",
            "--request",
            str(request),
            "--confirm",
            bootstrap.CONFIRMATION,
        ],
    )

    assert bootstrap.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "WP31_IDENTITY_BOOTSTRAP=FAIL category=BOOTSTRAP_RUNTIME_REJECTED\n"
    )
    assert "sensitive database host" not in captured.err
    assert "Traceback" not in captured.err


def test_workflow_has_one_fast_canary_path_and_no_source_database_identity_job() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    assert "greenfield-canary-fast" in workflow
    assert "FAST_CANARY_6894CD3_PRODUCTION_CANARY" in workflow
    assert "--database-kind canary" in workflow
    assert "greenfield_identity_bootstrap:" not in workflow
    assert "greenfield-identity-bootstrap" not in workflow
    fast_job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "inputs.phase == 'greenfield-canary-fast'" in fast_job
    assert "Create only the exact isolated canary database" in fast_job
    assert "Deploy exact zero-worker Canary" in fast_job
    assert "owner_user_id" in fast_job
    assert 'value["owner_roles"] == ["LEARNER","REVIEWER"]' in fast_job
    assert "Download exact preflight evidence before infrastructure access" in workflow
    assert "if: inputs.phase == 'greenfield-backup-restore' || inputs.phase == 'greenfield-deploy'" in workflow
