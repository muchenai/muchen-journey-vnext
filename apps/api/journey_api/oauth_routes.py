import uuid
from datetime import timedelta
from hmac import compare_digest
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.feishu_oauth import (
    FeishuOAuthClient,
    OAuthProviderError,
    get_feishu_oauth_client,
)
from journey_api.idempotency import canonical_hash, find_replay, store_result
from journey_api.identity import (
    OAUTH_COOKIE,
    add_audit,
    clear_oauth_cookie,
    credential_hash,
    derive_identity_link_token,
    enforce_auth_limit,
    random_token,
    set_oauth_cookie,
    set_session_cookies,
    utc_now,
)
from journey_api.models import (
    ExternalIdentity,
    ExternalIdentityLink,
    IdentityLinkStatus,
    IdentitySession,
    OAuthLoginState,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)
from journey_api.schemas import (
    CommandOut,
    CommandResponse,
    CreateIdentityLinkCommand,
    IdentityAccessListOut,
    IdentityAccessListResponse,
    IdentityAccessOut,
    IdentityLinkOut,
    IdentityLinkResponse,
    OAuthCallbackCommand,
    OAuthCallbackOut,
    OAuthCallbackResponse,
    OAuthStartCommand,
    OAuthStartOut,
    OAuthStartResponse,
    RevokeExternalIdentityCommand,
    RevokeIdentityLinkCommand,
)

router = APIRouter(prefix="/api/v1")
PROVIDER = "FEISHU"


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def safe_entry(role: Role) -> str:
    return {
        Role.REVIEWER: "/review",
        Role.OPERATOR: "/ops",
        Role.CONTENT_EDITOR: "/content",
    }[role]


def requested_role(return_to: str) -> Role:
    return {
        "/review": Role.REVIEWER,
        "/ops": Role.OPERATOR,
        "/content": Role.CONTENT_EDITOR,
    }[return_to]


def link_start_path(token: str, role: Role) -> str:
    return "/auth/feishu?" + urlencode(
        {"return_to": safe_entry(role), "link_token": token}
    )


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def require_feishu_enabled() -> None:
    if not get_settings().feishu_oauth_enabled:
        raise ApiError(503, "IDENTITY_PROVIDER_DISABLED", "真实身份登录尚未配置。")


@router.get("/ops/identity-access", response_model=IdentityAccessListResponse)
def list_identity_access(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    role_rows = session.execute(
        select(User, RoleAssignment.role)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role.in_(
                [Role.REVIEWER, Role.OPERATOR, Role.CONTENT_EDITOR]
            ),
        )
        .order_by(User.display_name, User.id, RoleAssignment.role)
        .limit(100)
    ).all()
    user_ids = {user.id for user, _role in role_rows}
    identities = (
        session.scalars(
            select(ExternalIdentity).where(
                ExternalIdentity.organization_id == actor.organization_id,
                ExternalIdentity.provider == PROVIDER,
                ExternalIdentity.user_id.in_(user_ids),
            )
        ).all()
        if user_ids
        else []
    )
    links = (
        session.scalars(
            select(ExternalIdentityLink).where(
                ExternalIdentityLink.organization_id == actor.organization_id,
                ExternalIdentityLink.provider == PROVIDER,
                ExternalIdentityLink.user_id.in_(user_ids),
            )
        ).all()
        if user_ids
        else []
    )

    identities_by_user: dict[uuid.UUID, ExternalIdentity] = {}
    for identity in identities:
        current = identities_by_user.get(identity.user_id)
        if current is None or (
            current.revoked_at is not None and identity.revoked_at is None
        ) or (
            current.revoked_at is not None
            and identity.revoked_at is not None
            and identity.verified_at > current.verified_at
        ):
            identities_by_user[identity.user_id] = identity

    links_by_user_role: dict[tuple[uuid.UUID, Role], ExternalIdentityLink] = {}
    for link in links:
        key = (link.user_id, link.role)
        current = links_by_user_role.get(key)
        if current is None or (link.created_at, link.id) > (current.created_at, current.id):
            links_by_user_role[key] = link

    now = utc_now()
    items: list[IdentityAccessOut] = []
    for user, role in role_rows:
        identity = identities_by_user.get(user.id)
        link = links_by_user_role.get((user.id, role))
        active_identity = identity is not None and identity.revoked_at is None
        active_link = (
            link is not None
            and link.status == IdentityLinkStatus.PENDING
            and link.expires_at > now
        )
        if active_identity:
            identity_status = "LINKED"
            allowed_commands = (
                [] if user.id == actor.id else ["revoke_external_identity"]
            )
        elif active_link:
            identity_status = "REVOKED" if identity is not None else "UNLINKED"
            allowed_commands = ["revoke_identity_link"]
        else:
            identity_status = "REVOKED" if identity is not None else "UNLINKED"
            allowed_commands = ["create_identity_link"]
        link_status = None
        if link is not None:
            link_status = (
                IdentityLinkStatus.EXPIRED.value
                if link.status == IdentityLinkStatus.PENDING and link.expires_at <= now
                else link.status.value
            )
        items.append(
            IdentityAccessOut(
                user_id=user.id,
                display_name=user.display_name,
                role=role.value,
                identity_id=identity.id if identity else None,
                identity_status=identity_status,
                identity_revision=identity.revision if identity else None,
                identity_verified_at=identity.verified_at if identity else None,
                is_current_actor=user.id == actor.id,
                link_id=link.id if link else None,
                link_status=link_status,
                link_revision=link.revision if link else None,
                link_expires_at=link.expires_at if link else None,
                allowed_commands=allowed_commands,
            )
        )
    return envelope(request, IdentityAccessListOut(items=items))


@router.post("/ops/identity-links", response_model=IdentityLinkResponse)
def create_identity_link(
    command: CreateIdentityLinkCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="identity_link.create",
        key=idempotency_key,
        payload=payload,
    )
    settings = get_settings()
    token = derive_identity_link_token(
        secret=settings.identity_subject_secret,
        actor_id=actor.id,
        idempotency_key=idempotency_key,
        request_hash=canonical_hash(payload),
    )
    if replay is not None:
        replay_role = Role(str(replay["role"]))
        return envelope(
            request,
            IdentityLinkOut(
                **replay,
                link_token=token,
                start_path=link_start_path(token, replay_role),
            ),
        )

    role = Role(command.role)
    target = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.target_user_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == role,
        )
        .with_for_update()
    )
    if target is None:
        raise ApiError(422, "VALIDATION_FAILED", "目标身份或角色无效。")
    active_identity = session.scalar(
        select(ExternalIdentity.id).where(
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.user_id == target.id,
            ExternalIdentity.provider == PROVIDER,
            ExternalIdentity.revoked_at.is_(None),
        )
    )
    if active_identity is not None:
        raise ApiError(409, "IDENTITY_ALREADY_LINKED", "目标身份已经绑定飞书。")
    now = utc_now()
    pending = session.scalar(
        select(ExternalIdentityLink)
        .where(
            ExternalIdentityLink.organization_id == actor.organization_id,
            ExternalIdentityLink.user_id == target.id,
            ExternalIdentityLink.role == role,
            ExternalIdentityLink.provider == PROVIDER,
            ExternalIdentityLink.status == IdentityLinkStatus.PENDING,
        )
        .with_for_update()
    )
    if pending is not None and pending.expires_at > now:
        raise ApiError(409, "IDENTITY_LINK_PENDING", "目标身份已有未过期绑定链接。")
    if pending is not None:
        pending.status = IdentityLinkStatus.EXPIRED
        pending.revision += 1

    expires_at = now + timedelta(minutes=command.expires_in_minutes)
    identity_link = ExternalIdentityLink(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        user_id=target.id,
        role=role,
        provider=PROVIDER,
        token_hash=credential_hash(settings.identity_subject_secret, "identity-link", token),
        status=IdentityLinkStatus.PENDING,
        expires_at=expires_at,
        created_by=actor.id,
        revision=1,
    )
    session.add(identity_link)
    result = {
        "id": str(identity_link.id),
        "target_user_id": str(target.id),
        "role": role.value,
        "status": identity_link.status.value,
        "expires_at": expires_at.isoformat(),
        "revision": identity_link.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="identity_link.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="identity_link.created",
        resource_type="external_identity_link",
        resource_id=identity_link.id,
        result="SUCCESS",
        details={"provider": PROVIDER, "role": role.value},
    )
    session.commit()
    return envelope(
        request,
        IdentityLinkOut(
            **result,
            link_token=token,
            start_path=link_start_path(token, role),
        ),
    )


@router.post(
    "/ops/identity-links/{link_id}/revoke",
    response_model=CommandResponse,
)
def revoke_identity_link(
    link_id: uuid.UUID,
    command: RevokeIdentityLinkCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    link = session.scalar(
        select(ExternalIdentityLink)
        .where(
            ExternalIdentityLink.id == link_id,
            ExternalIdentityLink.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if link is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的身份绑定链接。")
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="identity_link.revoke",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    ensure_revision(link.revision, command.expected_revision)
    if link.status != IdentityLinkStatus.PENDING:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前身份绑定链接不能撤销。")
    link.status = IdentityLinkStatus.REVOKED
    link.revoked_at = utc_now()
    link.revision += 1
    result = {
        "resource_id": str(link.id),
        "status": link.status.value,
        "revision": link.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="identity_link.revoke",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="identity_link.revoked",
        resource_type="external_identity_link",
        resource_id=link.id,
        result="SUCCESS",
        details={"provider": PROVIDER, "reason_provided": True},
    )
    session.commit()
    return envelope(request, CommandOut(**result))


@router.post(
    "/ops/external-identities/{identity_id}/revoke",
    response_model=CommandResponse,
)
def revoke_external_identity(
    identity_id: uuid.UUID,
    command: RevokeExternalIdentityCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    identity = session.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.id == identity_id,
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.provider == PROVIDER,
        )
        .with_for_update()
    )
    if identity is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的外部身份。")
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="external_identity.revoke",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    if identity.user_id == actor.id:
        raise ApiError(409, "SELF_REVOCATION_DENIED", "不能撤销当前登录使用的运营身份。")
    ensure_revision(identity.revision, command.expected_revision)
    if identity.revoked_at is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "外部身份已经撤销。")
    now = utc_now()
    identity.revoked_at = now
    identity.revision += 1
    active_sessions = session.scalars(
        select(IdentitySession)
        .where(
            IdentitySession.external_identity_id == identity.id,
            IdentitySession.revoked_at.is_(None),
        )
        .with_for_update()
    ).all()
    for active_session in active_sessions:
        active_session.revoked_at = now
    result = {
        "resource_id": str(identity.id),
        "status": "REVOKED",
        "revision": identity.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="external_identity.revoke",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="external_identity.revoked",
        resource_type="external_identity",
        resource_id=identity.id,
        result="SUCCESS",
        details={"provider": PROVIDER, "reason_provided": True},
    )
    session.commit()
    return envelope(request, CommandOut(**result))


@router.post("/auth/feishu/start", response_model=OAuthStartResponse)
def start_feishu_oauth(
    command: OAuthStartCommand,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    client: FeishuOAuthClient = Depends(get_feishu_oauth_client),
) -> dict[str, object]:
    require_feishu_enabled()
    settings = get_settings()
    enforce_auth_limit(
        request,
        scope="oauth.feishu.start",
        secret=settings.identity_subject_secret,
        limit=settings.oauth_attempt_limit,
        message="身份登录尝试过多，请稍后再试。",
    )
    link = None
    now = utc_now()
    if command.link_token:
        link = session.scalar(
            select(ExternalIdentityLink)
            .where(
                ExternalIdentityLink.token_hash
                == credential_hash(
                    settings.identity_subject_secret,
                    "identity-link",
                    command.link_token,
                )
            )
            .with_for_update()
        )
        if link is None or link.provider != PROVIDER:
            raise ApiError(410, "IDENTITY_LINK_INVALID", "身份绑定链接无效或已过期。")
        if link.status != IdentityLinkStatus.PENDING or link.expires_at <= now:
            if link.status == IdentityLinkStatus.PENDING:
                link.status = IdentityLinkStatus.EXPIRED
                link.revision += 1
                session.commit()
            raise ApiError(410, "IDENTITY_LINK_INVALID", "身份绑定链接无效或已过期。")
        if safe_entry(link.role) != command.return_to:
            raise ApiError(422, "VALIDATION_FAILED", "身份角色与返回入口不一致。")

    state = random_token()
    browser_token = random_token()
    expires_at = now + timedelta(minutes=settings.oauth_state_ttl_minutes)
    session.add(
        OAuthLoginState(
            id=uuid.uuid4(),
            provider=PROVIDER,
            state_hash=credential_hash(
                settings.identity_subject_secret, "oauth-state", state
            ),
            browser_token_hash=credential_hash(
                settings.identity_subject_secret, "oauth-browser", browser_token
            ),
            identity_link_id=link.id if link else None,
            return_to=command.return_to,
            expires_at=expires_at,
        )
    )
    session.commit()
    set_oauth_cookie(
        response,
        browser_token,
        max_age=settings.oauth_state_ttl_minutes * 60,
    )
    return envelope(
        request,
        OAuthStartOut(
            authorization_url=client.authorization_url(state),
            expires_at=expires_at,
        ),
    )


@router.post("/auth/feishu/callback", response_model=OAuthCallbackResponse)
def complete_feishu_oauth(
    command: OAuthCallbackCommand,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    client: FeishuOAuthClient = Depends(get_feishu_oauth_client),
) -> dict[str, object]:
    require_feishu_enabled()
    settings = get_settings()
    enforce_auth_limit(
        request,
        scope="oauth.feishu.callback",
        secret=settings.identity_subject_secret,
        limit=settings.oauth_attempt_limit,
        message="身份回调尝试过多，请稍后再试。",
    )
    browser_token = request.cookies.get(OAUTH_COOKIE, "")
    if not browser_token:
        raise ApiError(401, "OAUTH_BROWSER_MISMATCH", "身份登录上下文不存在或已过期。")
    state_row = session.scalar(
        select(OAuthLoginState)
        .where(
            OAuthLoginState.provider == PROVIDER,
            OAuthLoginState.state_hash
            == credential_hash(
                settings.identity_subject_secret, "oauth-state", command.state
            )
        )
        .with_for_update()
    )
    expected_browser_hash = credential_hash(
        settings.identity_subject_secret, "oauth-browser", browser_token
    )
    if state_row is None or not compare_digest(
        state_row.browser_token_hash, expected_browser_hash
    ):
        raise ApiError(401, "OAUTH_BROWSER_MISMATCH", "身份登录上下文不存在或已过期。")
    now = utc_now()
    if state_row.consumed_at is not None:
        raise ApiError(409, "OAUTH_STATE_REPLAY", "身份登录状态已经使用。")
    if state_row.expires_at <= now:
        state_row.consumed_at = now
        session.commit()
        raise ApiError(410, "OAUTH_STATE_EXPIRED", "身份登录状态已过期。")
    state_row.consumed_at = now
    identity_link_id = state_row.identity_link_id
    return_to = state_row.return_to
    session.commit()

    try:
        profile = client.exchange_code(command.code)
    except OAuthProviderError as exc:
        raise ApiError(
            502,
            "IDENTITY_PROVIDER_UNAVAILABLE",
            "飞书身份验证暂时不可用，请重新开始登录。",
            retryable=True,
        ) from exc
    subject_hash = credential_hash(
        settings.identity_subject_secret,
        f"external:{PROVIDER}:{settings.feishu_app_id}",
        profile.open_id,
    )
    identity = session.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.provider == PROVIDER,
            ExternalIdentity.subject == subject_hash,
        )
        .with_for_update()
    )
    if identity is not None and identity.revoked_at is not None:
        raise ApiError(403, "IDENTITY_REVOKED", "该外部身份已撤销。")

    role = requested_role(return_to)
    link = None
    if identity_link_id is not None:
        link = session.scalar(
            select(ExternalIdentityLink)
            .where(ExternalIdentityLink.id == identity_link_id)
            .with_for_update()
        )
        if (
            link is None
            or link.provider != PROVIDER
            or link.status != IdentityLinkStatus.PENDING
            or link.expires_at <= utc_now()
            or link.role != role
        ):
            raise ApiError(410, "IDENTITY_LINK_INVALID", "身份绑定链接无效或已过期。")
        if identity is not None and identity.user_id != link.user_id:
            raise ApiError(409, "IDENTITY_ALREADY_LINKED", "飞书身份已经绑定其他用户。")
        target_identity = session.scalar(
            select(ExternalIdentity.id).where(
                ExternalIdentity.organization_id == link.organization_id,
                ExternalIdentity.user_id == link.user_id,
                ExternalIdentity.provider == PROVIDER,
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        if identity is None and target_identity is not None:
            raise ApiError(409, "IDENTITY_ALREADY_LINKED", "目标身份已经绑定飞书。")
        if identity is None:
            identity = ExternalIdentity(
                id=uuid.uuid4(),
                organization_id=link.organization_id,
                user_id=link.user_id,
                provider=PROVIDER,
                subject=subject_hash,
                revision=1,
            )
            session.add(identity)
            session.flush()
        link.status = IdentityLinkStatus.CONSUMED
        link.consumed_at = utc_now()
        link.revision += 1
    elif identity is None:
        raise ApiError(403, "IDENTITY_NOT_LINKED", "该飞书身份尚未获得 vNext 访问权限。")

    assert identity is not None
    user = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == identity.user_id,
            User.organization_id == identity.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == identity.organization_id,
            RoleAssignment.role == role,
        )
        .with_for_update()
    )
    if user is None:
        raise ApiError(403, "FORBIDDEN", "当前身份没有该入口的有效权限。")

    issued_at = utc_now()
    previous_sessions = session.scalars(
        select(IdentitySession)
        .where(
            IdentitySession.user_id == user.id,
            IdentitySession.role == role,
            IdentitySession.revoked_at.is_(None),
        )
        .with_for_update()
    ).all()
    for previous in previous_sessions:
        previous.revoked_at = issued_at
    session_token = random_token()
    csrf_token = random_token()
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    identity_session = IdentitySession(
        id=uuid.uuid4(),
        organization_id=user.organization_id,
        user_id=user.id,
        external_identity_id=identity.id,
        role=role,
        token_hash=credential_hash(settings.session_secret, "session", session_token),
        csrf_token_hash=credential_hash(settings.session_secret, "csrf", csrf_token),
        expires_at=expires_at,
    )
    session.add(identity_session)
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="oauth.login_succeeded",
        resource_type="identity_session",
        resource_id=identity_session.id,
        result="SUCCESS",
        details={"provider": PROVIDER, "role": role.value},
    )
    session.commit()
    set_session_cookies(
        response,
        session_token,
        csrf_token,
        max_age=settings.session_ttl_hours * 3600,
    )
    clear_oauth_cookie(response)
    return envelope(
        request,
        OAuthCallbackOut(
            safe_entry=return_to,
            expires_at=expires_at,
            csrf_token=csrf_token,
        ),
    )
