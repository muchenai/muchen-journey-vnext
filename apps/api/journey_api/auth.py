from collections.abc import Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from datetime import UTC, datetime
from hmac import compare_digest

from fastapi import Depends, Header, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, STAFF_SESSION_COOKIE, STAFF_CSRF_COOKIE, credential_hash
from journey_api.reviewer_access import effective_roles
from journey_api.review_admin_models import PublishedTaskContent
from journey_api.models import (
    Assignment,
    CompletionCode,
    Enrollment,
    ExternalIdentity,
    IdentitySession,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)

TEMPORARY_IDENTITY_PROVIDERS = ("PHONE", "PHONE_PASSWORD")

@dataclass(frozen=True)
class Actor:
    id: UUID
    organization_id: UUID
    roles: frozenset[Role]
    display_name: str
    session_id: UUID | None = None
    entry_role: Role | None = None
    external_identity_verified: bool = False
    inherited_learner_id: UUID | None = None
    exploration_only: bool = False

    @property
    def learner_record_id(self) -> UUID:
        return self.inherited_learner_id or self.id

    def has_role(self, role: Role) -> bool:
        return role in self.roles


def enforce_canary_learner_scope(actor: Actor) -> Actor:
    settings = get_settings()
    if (
        settings.release_marker == "PRODUCTION_CANARY_UAT"
        and actor.has_role(Role.LEARNER)
        and actor.id not in set(settings.canary_learner_user_ids)
        and not (
            settings.feishu_learner_registration_enabled
            and actor.external_identity_verified
            and actor.organization_id == settings.feishu_learner_organization_id
        )
    ):
        raise ApiError(
            403,
            "CANARY_ACCESS_DENIED",
            "当前账号不在受控内测范围内。",
        )
    return actor


def enforce_canary_invite_target(target_user_id: UUID | None) -> None:
    """Fail closed for every route that can activate a Learner identity.

    Production Canary UAT never permits an untargeted invite, and an existing
    invite or pending join context cannot bypass a later allowlist change.
    """

    settings = get_settings()
    if (
        settings.release_marker == "PRODUCTION_CANARY_UAT"
        and target_user_id not in set(settings.canary_learner_user_ids)
    ):
        raise ApiError(
            403,
            "CANARY_ACCESS_DENIED",
            "受控内测邀请必须绑定当前允许的学员身份。",
        )


def inherited_learner_ids(session: Session, organization_id: UUID, user_ids: Sequence[UUID]) -> dict[UUID, UUID]:
    """Map current accounts to the owners of their inherited learning records."""
    if not user_ids:
        return {}
    return dict(session.execute(
        select(CompletionCode.migrated_to_user_id, CompletionCode.user_id).where(
            CompletionCode.organization_id == organization_id,
            CompletionCode.migrated_to_user_id.in_(user_ids),
            CompletionCode.used_at.is_not(None),
            CompletionCode.user_id != CompletionCode.migrated_to_user_id,
        )
    ).all())


def get_actor(
    request: Request,
    x_fixture_role: str | None = Header(default=None, alias="X-Fixture-Role"),
    session: Session = Depends(get_db),
) -> Actor:
    settings = get_settings()
    scope = request.headers.get("X-Journey-Session-Scope")
    if scope not in {None, "learner", "staff"}:
        raise ApiError(401, "UNAUTHENTICATED", "无效的登录入口。")
    learner_path = request.url.path.startswith("/api/v1/me/")
    if learner_path and scope == "staff":
        raise ApiError(403, "FORBIDDEN", "请从学员端登录。")
    staff = scope == "staff" or (scope is None and not learner_path and bool(request.cookies.get(STAFF_SESSION_COOKIE)))
    session_cookie = STAFF_SESSION_COOKIE if staff else SESSION_COOKIE
    csrf_cookie_name = STAFF_CSRF_COOKIE if staff else CSRF_COOKIE
    session_token = request.cookies.get(session_cookie)
    if session_token:
        token_hash = credential_hash(settings.session_secret, "session", session_token)
        row = session.execute(
            select(IdentitySession, User, ExternalIdentity.provider)
            .join(User, User.id == IdentitySession.user_id)
            .outerjoin(
                ExternalIdentity,
                ExternalIdentity.id == IdentitySession.external_identity_id,
            )
            .where(
                IdentitySession.token_hash == token_hash,
                IdentitySession.revoked_at.is_(None),
                IdentitySession.expires_at > datetime.now(UTC),
                User.status == UserStatus.ACTIVE,
                User.organization_id == IdentitySession.organization_id,
                or_(
                    IdentitySession.external_identity_id.is_(None),
                    and_(
                        ExternalIdentity.revoked_at.is_(None),
                        ExternalIdentity.user_id == IdentitySession.user_id,
                        ExternalIdentity.organization_id
                        == IdentitySession.organization_id,
                        ExternalIdentity.revision
                        == IdentitySession.external_identity_revision,
                    ),
                ),
            )
        ).first()
        if row is None:
            raise ApiError(401, "UNAUTHENTICATED", "vNext 会话无效或已过期。")
        identity_session, user, provider = row
        # A cookie or caller-controlled scope must never turn one entry into the other.
        if (staff and identity_session.role == Role.LEARNER) or ((scope == "learner" or learner_path) and identity_session.role != Role.LEARNER):
            raise ApiError(401, "UNAUTHENTICATED", "当前入口的登录已失效，请重新登录。")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and identity_session.role in {Role.REVIEWER, Role.OPERATOR, Role.CONTENT_EDITOR}:
            # Serialize staff writes with permission revocation. A request that
            # waited for the user lock must not continue using an old session.
            session.scalar(select(User.id).where(User.id == user.id).with_for_update())
            identity_session = session.scalar(select(IdentitySession).where(
                IdentitySession.id == identity_session.id).execution_options(populate_existing=True))
            if identity_session is None or identity_session.revoked_at is not None:
                raise ApiError(401, "UNAUTHENTICATED", "管理端会话已失效，请重新登录。")
        roles = frozenset(
            session.scalars(
                select(RoleAssignment.role).where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.organization_id == user.organization_id,
                )
            ).all()
        )
        roles = effective_roles(user.id, roles)
        from journey_api.review_admin_access import filter_staff_roles
        roles = filter_staff_roles(session, user.id, user.organization_id, roles)
        if not roles:
            raise ApiError(401, "UNAUTHENTICATED", "当前会话已不具备任何有效权限。")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf_cookie = request.cookies.get(csrf_cookie_name, "")
            csrf_header = request.headers.get("X-CSRF-Token", "")
            expected_hash = credential_hash(settings.session_secret, "csrf", csrf_header)
            if (
                not csrf_cookie
                or not csrf_header
                or not compare_digest(csrf_cookie, csrf_header)
                or not compare_digest(identity_session.csrf_token_hash, expected_hash)
            ):
                raise ApiError(403, "FORBIDDEN", "安全校验失败，请刷新后重试。")
        exploration_only = False
        if identity_session.role == Role.LEARNER and provider in (*TEMPORARY_IDENTITY_PROVIDERS, "NICKNAME_PHONE"):
            exploration_only = session.scalar(select(ExternalIdentity.id).where(
                ExternalIdentity.user_id == user.id, ExternalIdentity.organization_id == user.organization_id,
                ExternalIdentity.provider == "FEISHU", ExternalIdentity.revoked_at.is_(None),
            ).limit(1)) is None
        actor = enforce_canary_learner_scope(
            Actor(
                user.id,
                user.organization_id,
                roles,
                user.display_name,
                identity_session.id,
                identity_session.role if identity_session.role in roles else None,
                identity_session.external_identity_id is not None,
                exploration_only=exploration_only,
            )
        )
        # Authenticate and enforce the corporate account's scope before resolving
        # access to inherited history. Never transfer identity or staff roles.
        inherited_learner_id = inherited_learner_ids(session, user.organization_id, [user.id]).get(user.id)
        return replace(actor, inherited_learner_id=inherited_learner_id)
    if not settings.allow_fixture_identity or settings.app_env not in {"local", "test"}:
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的 vNext 会话。")
    try:
        requested_role = Role((x_fixture_role or "").upper())
    except ValueError as exc:
        raise ApiError(401, "UNAUTHENTICATED", "本地 fixture 身份无效。") from exc
    row = session.execute(
        select(User, RoleAssignment)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(RoleAssignment.role == requested_role, User.status == UserStatus.ACTIVE)
    ).first()
    if row is None:
        raise ApiError(401, "UNAUTHENTICATED", "本地 fixture 身份不存在。")
    user, assignment = row
    return enforce_canary_learner_scope(
        Actor(
            user.id,
            user.organization_id,
            effective_roles(user.id, frozenset({assignment.role})),
            user.display_name,
            None,
            assignment.role,
        )
    )


def require_role(actor: Actor, role: Role) -> None:
    if role not in effective_roles(actor.id, actor.roles):
        raise ApiError(403, "FORBIDDEN", "当前身份无权执行此操作。")


def get_learner_actor(actor: Actor = Depends(get_actor)) -> Actor:
    """Resolve only learner operations to the inherited immutable record owner.

    Session/staff endpoints retain the authenticated corporate user. Never grant
    the retired phone record staff roles, or change the corporate identity.
    """
    require_role(actor, Role.LEARNER)
    if actor.inherited_learner_id is None:
        return actor
    return replace(actor, id=actor.inherited_learner_id,
                   roles=frozenset({Role.LEARNER}), entry_role=Role.LEARNER)


def require_company_learner(actor: Actor) -> None:
    if actor.exploration_only:
        raise ApiError(403, "COMPANY_ACCOUNT_REQUIRED", "请用公司认证的飞书账号进行登录和使用")


def get_company_learner_actor(actor: Actor = Depends(get_learner_actor)) -> Actor:
    require_company_learner(actor)
    return actor


def require_assignment_camp(session: Session, actor: Actor, assignment_id: UUID) -> None:
    if not actor.exploration_only:
        return
    # Both dynamic exploration and village tasks populate novice_task_id.
    # The immutable publication identifies the camp for this assignment.
    claimed_task = session.execute(
        select(PublishedTaskContent.content["camp"].as_string())
        .select_from(Assignment)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .outerjoin(PublishedTaskContent, and_(
            PublishedTaskContent.task_version_id == Assignment.task_version_id,
            PublishedTaskContent.organization_id == Assignment.organization_id,
        ))
        .where(Assignment.id == assignment_id, Assignment.organization_id == actor.organization_id,
               Enrollment.organization_id == actor.organization_id, Enrollment.learner_id == actor.id,
               Enrollment.novice_task_id.is_not(None))
    ).first()
    if claimed_task is not None and claimed_task[0] != "exploration":
        require_company_learner(actor)


def get_assignment_learner_actor(
    assignment_id: UUID, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)
) -> Actor:
    require_assignment_camp(session, actor, assignment_id)
    return actor
