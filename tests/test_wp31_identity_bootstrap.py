import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts import wp31_identity_bootstrap as bootstrap
from scripts import wp31_prepare_greenfield_canary as prepare_canary


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _BootstrapSession:
    def __init__(
        self,
        organizations: list[object],
        *,
        existing_users: list[object] | None = None,
        role_assignments: list[object] | None = None,
    ) -> None:
        self.organizations = organizations
        self.existing_users = {
            getattr(user, "id"): user for user in (existing_users or [])
        }
        self.role_assignments = role_assignments or []
        self.added: list[object] = []

    def scalars(self, statement: object) -> _ScalarRows:
        descriptions = getattr(statement, "column_descriptions", [])
        entity = descriptions[0].get("entity") if descriptions else None
        if getattr(entity, "__name__", None) == "Organization":
            return _ScalarRows(self.organizations)
        if getattr(entity, "__name__", None) == "User":
            return _ScalarRows(list(self.existing_users.values()))
        if getattr(entity, "__name__", None) == "RoleAssignment":
            return _ScalarRows(self.role_assignments)
        return _ScalarRows([])

    def scalar(self, statement: object) -> object | None:
        parameters = getattr(statement, "compile")().params
        for value in parameters.values():
            if value in self.existing_users:
                return value
        return None

    def get(self, _model: object, identity: object) -> object | None:
        return self.existing_users.get(identity)

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


def _matching_existing_identities(
    request: bootstrap.BootstrapRequest,
    organization: object,
) -> tuple[list[object], list[object]]:
    from journey_api.models import Role, RoleAssignment, User, UserStatus

    users = [
        User(
            id=request.operator_user_id,
            organization_id=getattr(organization, "id"),
            display_name=request.operator_display_name,
            status=UserStatus.ACTIVE,
        ),
        User(
            id=request.learner_user_id,
            organization_id=getattr(organization, "id"),
            display_name=request.learner_display_name,
            status=UserStatus.ACTIVE,
        ),
        User(
            id=request.owner_user_id,
            organization_id=getattr(organization, "id"),
            display_name=request.owner_display_name,
            status=UserStatus.ACTIVE,
        ),
    ]
    assignments = [
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=getattr(organization, "id"),
            user_id=request.operator_user_id,
            role=Role.OPERATOR,
        ),
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=getattr(organization, "id"),
            user_id=request.operator_user_id,
            role=Role.REVIEWER,
        ),
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=getattr(organization, "id"),
            user_id=request.owner_user_id,
            role=Role.LEARNER,
        ),
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=getattr(organization, "id"),
            user_id=request.owner_user_id,
            role=Role.REVIEWER,
        ),
    ]
    return users, assignments


def test_request_parser_accepts_exact_non_sensitive_shape(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(_request(), ensure_ascii=False) + "\n", encoding="utf-8")

    parsed = bootstrap.parse_request(path)

    assert parsed.operator_display_name == "许瀚文"
    assert parsed.learner_display_name == "组长"
    assert parsed.expires_in_minutes == 15
    assert parsed.operator_user_id.version == 4
    assert parsed.learner_user_id.version == 4


def test_request_contract_wrapper_returns_a_stable_stage_category(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.parse_request_contract(path)

    assert captured.value.category == "REQUEST_CONTRACT_REJECTED"
    assert str(captured.value) == "identity bootstrap request contract rejected"


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


def test_runtime_contract_wrapper_returns_a_stable_stage_category() -> None:
    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.validate_runtime_contract(
            "postgresql+psycopg://journey_next_migrator:pw@private.rds.example:5432/other",
            app_env="production",
            release_marker="PRODUCTION_CANARY_UAT",
            confirmation=bootstrap.CONFIRMATION,
            database_kind="canary",
        )

    assert captured.value.category == "RUNTIME_CONTRACT_REJECTED"
    assert str(captured.value) == "identity bootstrap runtime contract rejected"


def test_application_settings_contract_validates_without_opening_a_database() -> None:
    settings = SimpleNamespace(
        database_url=(
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        app_env="production",
        release_marker="PRODUCTION_CANARY_UAT",
        identity_subject_secret="d" * 32,
        session_secret="s" * 32,
        invite_secret="i" * 32,
        import_signing_key="k" * 32,
    )
    database_settings = SimpleNamespace(
        database_url=settings.database_url,
        db_pool_size=8,
        db_max_overflow=2,
        db_pool_timeout_seconds=5,
    )

    assert bootstrap.validate_application_settings_contract(
        settings,
        database_settings,
        confirmation=bootstrap.CONFIRMATION,
        database_kind="canary",
    ) is None


@pytest.mark.parametrize("secret", ["short", "s" * 32 + "\n"])
def test_identity_secret_contract_wrapper_returns_a_stable_stage_category(
    secret: str,
) -> None:
    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.validate_identity_secret(secret)

    assert captured.value.category == "IDENTITY_SECRET_REJECTED"
    assert str(captured.value) == "identity subject secret contract rejected"


def test_identity_secret_set_rejects_reuse_with_stable_category() -> None:
    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.validate_identity_secret_set(
            identity_secret="d" * 32,
            session_secret="s" * 32,
            invite_secret="s" * 32,
            import_signing_key="k" * 32,
        )

    assert captured.value.category == "IDENTITY_SECRET_REJECTED"


def test_application_settings_contract_rejects_invalid_database_pool() -> None:
    settings = SimpleNamespace(
        database_url=(
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        app_env="production",
        release_marker="PRODUCTION_CANARY_UAT",
        identity_subject_secret="d" * 32,
        session_secret="s" * 32,
        invite_secret="i" * 32,
        import_signing_key="k" * 32,
    )
    database_settings = SimpleNamespace(
        database_url=settings.database_url,
        db_pool_size=26,
        db_max_overflow=2,
        db_pool_timeout_seconds=5,
    )

    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.validate_application_settings_contract(
            settings,
            database_settings,
            confirmation=bootstrap.CONFIRMATION,
            database_kind="canary",
        )

    assert captured.value.category == "RUNTIME_CONTRACT_REJECTED"


def test_prepare_env_file_is_owner_only_at_creation(tmp_path: Path) -> None:
    target = tmp_path / "safe.env"
    prepare_canary.write_env(target, {"SYNTHETIC_VALUE": "not-sensitive"})

    assert target.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_contract_only_cli_validates_without_importing_application_dependencies(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(_request(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(tmp_path),
        "APP_ENV": "production",
        "RELEASE_MARKER": "PRODUCTION_CANARY_UAT",
        "DATABASE_URL": (
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        "IDENTITY_SUBJECT_SECRET": "d" * 32,
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
            "--contract-only",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "identity_contract_probe": "PASS",
        "request_contract": "PASS",
        "runtime_contract": "PASS",
        "identity_secret_contract": "PASS",
        "request_field_count": 8,
        "request_identity_count": 3,
    }
    assert result.stderr == ""


def test_contract_only_accepts_the_request_from_stdin(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(tmp_path),
        "APP_ENV": "production",
        "RELEASE_MARKER": "PRODUCTION_CANARY_UAT",
        "DATABASE_URL": (
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        "IDENTITY_SUBJECT_SECRET": "d" * 32,
    }

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "wp31_identity_bootstrap.py"),
            "--database-kind",
            "canary",
            "--request",
            "-",
            "--confirm",
            bootstrap.CONFIRMATION,
            "--contract-only",
        ],
        cwd=root,
        env=environment,
        input=json.dumps(_request(), ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["identity_contract_probe"] == "PASS"
    assert result.stderr == ""


def test_contract_only_settings_check_loads_config_without_opening_a_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        session_secret="s" * 32,
        invite_secret="i" * 32,
        import_signing_key="k" * 32,
    )
    config_module.get_database_settings = lambda: SimpleNamespace(
        database_url=(
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        db_pool_size=8,
        db_max_overflow=2,
        db_pool_timeout_seconds=5,
    )
    monkeypatch.setitem(sys.modules, "journey_api.config", config_module)
    monkeypatch.setenv("IDENTITY_SUBJECT_SECRET", "d" * 32)
    monkeypatch.setenv("SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("INVITE_SECRET", "i" * 32)
    monkeypatch.setenv("IMPORT_SIGNING_KEY", "k" * 32)
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
            "--contract-only",
            "--settings-check",
        ],
    )

    assert bootstrap.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "identity_contract_probe": "PASS",
        "request_contract": "PASS",
        "runtime_contract": "PASS",
        "identity_secret_contract": "PASS",
        "request_field_count": 8,
        "request_identity_count": 3,
    }
    assert captured.err == ""


def test_settings_check_requires_contract_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = tmp_path / "request.json"
    request.write_text(json.dumps(_request()) + "\n", encoding="utf-8")
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
            "--settings-check",
        ],
    )

    assert bootstrap.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "WP31_IDENTITY_BOOTSTRAP=FAIL category=RUNTIME_CONTRACT_REJECTED\n"


def test_contract_only_cli_builds_the_same_runtime_contract_from_source_secrets(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(_request(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(tmp_path),
        "WP08_MIGRATION_DB_PASSWORD": "m" * 24,
        "WP09_IDENTITY_SUBJECT_SECRET": "d" * 32,
        "WP15_SESSION_SECRET": "s" * 32,
        "WP15_INVITE_SECRET": "i" * 32,
        "WP15_IMPORT_SIGNING_KEY": "k" * 32,
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
            "--contract-only",
            "--rds-host",
            "private.rds.example",
            "--rds-port",
            "5432",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["runtime_contract"] == "PASS"
    assert result.stderr == ""


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


def test_bootstrap_reuses_three_exact_existing_controlled_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import identity as identity_module
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization

    business = Organization(id=uuid.uuid4(), name="Muchen Journey")
    request = bootstrap.parse_payload(_request())
    users, assignments = _matching_existing_identities(request, business)
    session = _BootstrapSession(
        [business],
        existing_users=users,
        role_assignments=assignments,
    )
    creation_audits: list[str] = []
    monkeypatch.setattr(
        identity_module,
        "add_audit",
        lambda *args, **kwargs: creation_audits.append(kwargs["action"]),
    )

    def create_replacement_link(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["target_user_id"] == request.operator_user_id
        return {
            "link_id": "replacement-link",
            "start_path": "/auth/feishu?return_to=%2Fops&link_token=replacement",
            "expires_at": "2026-09-08T04:15:00+00:00",
            "expires_in_minutes": 15,
        }

    monkeypatch.setattr(
        wp09_bootstrap,
        "create_operator_link",
        create_replacement_link,
    )

    result = bootstrap.bootstrap(
        session,
        request,
        "identity-subject-secret-with-32-bytes",
    )

    assert result["operator_link_id"] == "replacement-link"
    assert session.added == []
    assert creation_audits == []


def test_bootstrap_rejects_existing_identities_with_wrong_role_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import identity as identity_module
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization, Role

    business = Organization(id=uuid.uuid4(), name="Muchen Journey")
    request = bootstrap.parse_payload(_request())
    users, assignments = _matching_existing_identities(request, business)
    assignments = [
        assignment
        for assignment in assignments
        if not (
            assignment.user_id == request.owner_user_id
            and assignment.role == Role.REVIEWER
        )
    ]
    session = _BootstrapSession(
        [business],
        existing_users=users,
        role_assignments=assignments,
    )
    monkeypatch.setattr(identity_module, "add_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        wp09_bootstrap,
        "create_operator_link",
        lambda *args, **kwargs: {
            "link_id": "must-not-be-created",
            "start_path": "/auth/feishu?link_token=must-not-be-created",
            "expires_at": "2026-09-08T04:15:00+00:00",
            "expires_in_minutes": 15,
        },
    )

    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.bootstrap(
            session,
            request,
            "identity-subject-secret-with-32-bytes",
        )

    assert captured.value.category == "IDENTITY_STATE_REJECTED"


def test_bootstrap_rejects_partial_existing_identity_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization

    business = Organization(id=uuid.uuid4(), name="Muchen Journey")
    request = bootstrap.parse_payload(_request())
    users, assignments = _matching_existing_identities(request, business)
    session = _BootstrapSession(
        [business],
        existing_users=users[:2],
        role_assignments=assignments,
    )

    def must_not_create_link(*_args: object, **_kwargs: object) -> None:
        pytest.fail("partial identity state must be rejected before link creation")

    monkeypatch.setattr(wp09_bootstrap, "create_operator_link", must_not_create_link)

    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.bootstrap(
            session,
            request,
            "identity-subject-secret-with-32-bytes",
        )

    assert captured.value.category == "IDENTITY_STATE_REJECTED"


@pytest.mark.parametrize("mismatch", ["display_name", "status", "organization"])
def test_bootstrap_rejects_existing_identities_with_mismatched_attributes(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps" / "api"))
    from journey_api import wp09_bootstrap
    from journey_api.models import Organization, UserStatus

    business = Organization(id=uuid.uuid4(), name="Muchen Journey")
    request = bootstrap.parse_payload(_request())
    users, assignments = _matching_existing_identities(request, business)
    if mismatch == "display_name":
        users[0].display_name = "Unexpected Operator"
    elif mismatch == "status":
        users[1].status = UserStatus.DISABLED
    else:
        users[2].organization_id = uuid.uuid4()
    session = _BootstrapSession(
        [business],
        existing_users=users,
        role_assignments=assignments,
    )
    monkeypatch.setattr(
        wp09_bootstrap,
        "create_operator_link",
        lambda *args, **kwargs: {
            "link_id": "must-not-be-created",
            "start_path": "/auth/feishu?link_token=must-not-be-created",
            "expires_at": "2026-09-08T04:15:00+00:00",
            "expires_in_minutes": 15,
        },
    )

    with pytest.raises(bootstrap.BootstrapError) as captured:
        bootstrap.bootstrap(
            session,
            request,
            "identity-subject-secret-with-32-bytes",
        )

    assert captured.value.category == "IDENTITY_STATE_REJECTED"


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
    assert result.stderr == "WP31_IDENTITY_BOOTSTRAP=FAIL category=REQUEST_CONTRACT_REJECTED\n"
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
        session_secret="s" * 32,
        invite_secret="i" * 32,
        import_signing_key="k" * 32,
    )
    config_module.get_database_settings = lambda: SimpleNamespace(
        database_url=(
            "postgresql+psycopg://journey_next_migrator:dummy-password@"
            "private.rds.example:5432/journey_next_canary_20260901_c72fea5"
            "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
        ),
        db_pool_size=8,
        db_max_overflow=2,
        db_pool_timeout_seconds=5,
    )
    db_module = ModuleType("journey_api.db")

    def fail_session() -> None:
        raise RuntimeError("sensitive database host and SQL parameters")

    db_module.SessionLocal = fail_session
    monkeypatch.setitem(sys.modules, "journey_api.config", config_module)
    monkeypatch.setitem(sys.modules, "journey_api.db", db_module)
    monkeypatch.setenv("SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("INVITE_SECRET", "i" * 32)
    monkeypatch.setenv("IMPORT_SIGNING_KEY", "k" * 32)
    monkeypatch.setenv("IDENTITY_SUBJECT_SECRET", "d" * 32)
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
    assert "FAST_CANARY_FF1623C_PRODUCTION_CANARY" in workflow
    assert "--database-kind canary" in workflow
    assert "greenfield_identity_bootstrap:" not in workflow
    assert "greenfield-identity-bootstrap" not in workflow
    fast_job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "inputs.phase == 'greenfield-canary-fast'" in fast_job
    assert "Create only the exact isolated canary database" in fast_job
    assert "Deploy exact zero-worker Canary" in fast_job
    assert "scripts/wp31_identity_result.py encrypt" in fast_job
    assert "Download exact preflight evidence before infrastructure access" in workflow
    assert "if: inputs.phase == 'greenfield-backup-restore' || inputs.phase == 'greenfield-deploy'" in workflow
    minimal_probe = "Preflight identity request and secret contract before bundle creation"
    image_probe = "Preflight candidate image settings before infrastructure mutation"
    assert minimal_probe in workflow
    assert image_probe in workflow
    assert "--contract-only" in workflow
    prepare = "Prepare exact owner-only canary bundle after minimal contract probe"
    assert prepare in workflow
    assert workflow.index(minimal_probe) < workflow.index(prepare)
    assert workflow.index(prepare) < workflow.index(image_probe)
    assert workflow.index(image_probe) < workflow.index("Open bounded SSH ingress")
    assert workflow.index(image_probe) < workflow.index("Create only the exact isolated canary database")
    assert "inputs.phase == 'greenfield-preflight' || inputs.phase == 'greenfield-canary-fast'" in workflow
    minimal_block = workflow[workflow.index(minimal_probe) : workflow.index(prepare)]
    assert "--rds-host" in minimal_block
    assert "--request -" in minimal_block
    assert "wp31_prepare_greenfield_canary.py" not in minimal_block
    probe_block = workflow[workflow.index(image_probe) : workflow.index("Open bounded SSH ingress")]
    assert "--settings-check" in probe_block
    assert "--env-file" in probe_block
    assert "--network none" in probe_block
    assert "--request -" in probe_block
    assert "base64 --decode" in probe_block
    assert "DOCKER_CONFIG" in probe_block
    assert ". \"$RUNNER_TEMP/wp31-bundle/secrets/target-facts.env\"" not in probe_block
    assert "set -a" not in probe_block
    assert workflow.count("--request -") >= 2
    assert "-v '$remote/request.json:/tmp/request.json:ro'" not in workflow
    assert "chmod 0600 \"$bundle/request.json\"" in workflow
    identity_step = workflow[
        workflow.index("Bootstrap three controlled identities inside isolated Canary database") :
        workflow.index("Upload encrypted identity bootstrap result")
    ]
    assert 'image="$(awk -F=' in identity_step
    assert "image='ghcr.io/muchenai/muchen-journey-vnext-api@sha256:" not in identity_step
    assert 'cp scripts/wp31_exec_env.py "$bundle/wp31_exec_env.py"' in fast_job
    assert "python3 ./wp31_exec_env.py --env-file ./secrets/backup.env" in fast_job
    assert "python3 ./wp31_exec_env.py --env-file ./.deployment.env --env-file ./secrets/backup.env" in fast_job
    assert ". ./secrets/backup.env" not in fast_job
    upload = workflow[workflow.index("Upload exact expiring preflight evidence") : workflow.index("Verify in-run preflight evidence")]
    assert "inputs.phase == 'greenfield-preflight'" in upload
    assert "inputs.phase == 'greenfield-canary-fast'" not in upload
