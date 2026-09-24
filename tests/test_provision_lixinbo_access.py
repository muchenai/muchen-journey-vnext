import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import provision_lixinbo_access as provisioner


REMOTE_SCRIPT = Path(__file__).parents[1] / "scripts" / "provision_lixinbo_remote.sh"


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)


class Session:
    def __init__(self, organization, *, user=None, same_name=None, assignments=None):
        self.organization = organization
        self.user = user
        self.same_name = same_name or ([] if user is None else [user])
        self.assignments = assignments or []
        self.added = []
        self.commits = 0

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity.__name__ == "Organization":
            return Rows([self.organization])
        if entity.__name__ == "User":
            return Rows(self.same_name)
        if entity.__name__ == "RoleAssignment":
            return Rows(self.assignments)
        raise AssertionError(entity)

    def get(self, _model, identity):
        return self.user if self.user is not None and self.user.id == identity else None

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1


@pytest.fixture
def models():
    from journey_api.models import Organization, Role, RoleAssignment, User, UserStatus

    return SimpleNamespace(
        Organization=Organization,
        Role=Role,
        RoleAssignment=RoleAssignment,
        User=User,
        UserStatus=UserStatus,
    )


def organization(models):
    return models.Organization(id=uuid.uuid4(), name="Muchen Journey")


def test_remote_runtime_selection_does_not_parse_compose_files():
    script = REMOTE_SCRIPT.read_text()

    assert "docker compose ps" not in script
    assert "compose.sh" not in script
    assert "label=com.docker.compose.service=api" in script
    assert "com.docker.compose.project.working_dir" in script


def test_creates_exact_user_and_both_roles(monkeypatch, models):
    audits = []
    monkeypatch.setattr("journey_api.identity.add_audit", lambda _session, **kwargs: audits.append(kwargs))
    session = Session(organization(models))

    result = provisioner.provision(session)

    users = [item for item in session.added if isinstance(item, models.User)]
    roles = [item.role for item in session.added if isinstance(item, models.RoleAssignment)]
    assert [(user.id, user.display_name) for user in users] == [
        (provisioner.TARGET_USER_ID, provisioner.TARGET_DISPLAY_NAME)
    ]
    assert set(roles) == {models.Role.OPERATOR, models.Role.REVIEWER}
    assert {entry["action"] for entry in audits} == {
        "internal_access.user_created",
        "internal_access.role_granted",
    }
    assert result["effective_roles"] == ["OPERATOR", "REVIEWER"]
    assert session.commits == 1


def test_idempotent_when_exact_roles_exist(monkeypatch, models):
    monkeypatch.setattr("journey_api.identity.add_audit", lambda *_args, **_kwargs: None)
    org = organization(models)
    user = models.User(
        id=provisioner.TARGET_USER_ID,
        organization_id=org.id,
        display_name=provisioner.TARGET_DISPLAY_NAME,
        status=models.UserStatus.ACTIVE,
    )
    assignments = [
        models.RoleAssignment(id=uuid.uuid4(), organization_id=org.id, user_id=user.id, role=role)
        for role in (models.Role.OPERATOR, models.Role.REVIEWER)
    ]
    session = Session(org, user=user, assignments=assignments)

    result = provisioner.provision(session)

    assert session.added == []
    assert result["created_user"] is False
    assert result["added_roles"] == []
    assert session.commits == 1


def test_rejects_same_name_on_different_user(models):
    org = organization(models)
    other = models.User(
        id=uuid.uuid4(),
        organization_id=org.id,
        display_name=provisioner.TARGET_DISPLAY_NAME,
        status=models.UserStatus.ACTIVE,
    )
    session = Session(org, same_name=[other])

    with pytest.raises(provisioner.ProvisionError, match="different user"):
        provisioner.provision(session)

    assert session.commits == 0
