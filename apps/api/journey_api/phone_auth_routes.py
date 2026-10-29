import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from typing import Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.identity import (
    add_audit,
    credential_hash,
    enforce_auth_limit,
    random_token,
    set_session_cookies,
    utc_now,
)
from journey_api.learner_oauth import lock_learner_organization, provision_learner
from journey_api.learner_phone import remember_verified_phone
from journey_api.models import (
    AuditEntry,
    Assignment,
    AssignmentStatus,
    CompletionCode,
    Enrollment,
    ExternalIdentity,
    IdentitySession,
    PhonePasswordCredential,
    PhoneOtpChallenge,
    Role,
    RoleAssignment,
    Submission,
    SubmissionDraft,
    LearningMaterialCompletion,
    User,
    UserStatus,
)
from journey_api.sms import SmsDeliveryError, VolcengineSmsClient

router = APIRouter(prefix="/api/v1")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
LOCAL_CODE = "123456"
TEMPORARY_IDENTITY_PROVIDERS = ("PHONE", "PHONE_PASSWORD")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestPhoneCode(StrictModel):
    phone: str
    purpose: Literal["login", "register", "reset"] = "login"


class VerifyPhoneCode(StrictModel):
    phone: str
    code: str


class PhonePasswordLogin(StrictModel):
    phone: str
    password: str


class VerifiedPhonePassword(PhonePasswordLogin):
    code: str


class MigrateCompletionCode(StrictModel):
    code: str


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


class LearnerNickname(StrictModel):
    display_name: str


def phone_profile_allowed(session: Session, actor: Actor) -> bool:
    identity_session = session.get(IdentitySession, actor.session_id) if actor.session_id else None
    identity = session.get(ExternalIdentity, identity_session.external_identity_id) if identity_session else None
    corporate = session.scalar(select(ExternalIdentity.id).where(
        ExternalIdentity.user_id == actor.id,
        ExternalIdentity.organization_id == actor.organization_id,
        ExternalIdentity.provider == "FEISHU", ExternalIdentity.revoked_at.is_(None),
    ))
    return bool(identity and identity.user_id == actor.id
                and identity.provider in (*TEMPORARY_IDENTITY_PROVIDERS, "NICKNAME_PHONE")
                and corporate is None)


def nickname_needed(session: Session, user: User) -> bool:
    if user.display_name != "探索者":
        return False
    # An explicitly chosen placeholder is also a completed nickname setup.
    return session.scalar(select(AuditEntry.id).where(
        AuditEntry.organization_id == user.organization_id,
        AuditEntry.actor_id == user.id,
        AuditEntry.action == "learner.nickname_saved",
    ).limit(1)) is None


@router.get("/me/learner-profile")
def learner_profile(request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    user = session.get(User, actor.id)
    return envelope(request, {"display_name": user.display_name,
        "needs_nickname": phone_profile_allowed(session, actor) and nickname_needed(session, user)})


@router.put("/me/learner-profile")
def save_learner_nickname(payload: LearnerNickname, request: Request,
                          actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    if not phone_profile_allowed(session, actor):
        raise ApiError(403, "PHONE_ACCOUNT_REQUIRED", "仅手机号账号可设置昵称。")
    name = payload.display_name.strip()
    if not 1 <= len(name) <= 120 or any(ord(char) < 32 for char in name):
        raise ApiError(422, "VALIDATION_FAILED", "请输入 1–120 个字符的昵称。")
    user = session.scalar(select(User).where(User.id == actor.id,
        User.organization_id == actor.organization_id).with_for_update())
    if not nickname_needed(session, user):
        if user.display_name != name:
            raise ApiError(409, "NICKNAME_ALREADY_SET", "昵称已保存，请刷新页面进入探索营。")
        return envelope(request, {"display_name": user.display_name, "needs_nickname": False})
    user.display_name = name
    add_audit(session, request_id=request.state.request_id, action="learner.nickname_saved",
              resource_type="user", resource_id=user.id, actor_id=user.id,
              organization_id=actor.organization_id, result="SUCCESS")
    session.commit()
    return envelope(request, {"display_name": name, "needs_nickname": False})


def normalized_phone(value: str) -> str:
    phone = re.sub(r"[\s-]", "", value)
    if phone.startswith("+86"):
        phone = phone[3:]
    if not PHONE_PATTERN.fullmatch(phone):
        raise ApiError(422, "PHONE_INVALID", "请输入正确的中国大陆手机号。")
    return phone


def phone_subject(phone: str) -> str:
    settings = get_settings()
    return credential_hash(settings.identity_subject_secret, "phone-subject", phone)


def validate_password(value: str) -> str:
    if not 6 <= len(value) <= 11 or any(character.isspace() for character in value):
        raise ApiError(422, "PASSWORD_INVALID", "密码需为 6–11 个字符，且不能包含空格。")
    return value


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 310_000)
    return actual_salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    _, actual_hash = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(actual_hash, expected_hash)


def password_phone_identity(session: Session, subject: str) -> ExternalIdentity | None:
    """Never recreate a retired phone account or silently merge different users."""
    identities = session.scalars(select(ExternalIdentity).where(
        ExternalIdentity.provider.in_(("PHONE_PASSWORD", "PHONE", "NICKNAME_PHONE")),
        ExternalIdentity.subject == subject,
    ).with_for_update()).all()
    if any(identity.revoked_at is not None for identity in identities):
        raise ApiError(409, "ACCOUNT_MIGRATED", "该账号已完成迁移，请使用企业飞书登录。")
    if len({identity.user_id for identity in identities}) > 1:
        raise ApiError(409, "PHONE_ACCOUNT_CONFLICT", "该手机号存在多个历史账号，请联系管理员李鑫波处理。")
    return next((identity for identity in identities if identity.provider == "PHONE_PASSWORD"),
                identities[0] if identities else None)


def consume_phone_code(session: Session, subject: str, code: str, purpose: str) -> PhoneOtpChallenge:
    settings = get_settings()
    # Always use the newest challenge, including consumed ones: an older code
    # must not become valid again after the newest one has been used.
    challenge = session.scalar(select(PhoneOtpChallenge).where(
        PhoneOtpChallenge.phone_subject == subject,
    ).order_by(PhoneOtpChallenge.created_at.desc(), PhoneOtpChallenge.id.desc()).with_for_update())
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= utc_now():
        raise ApiError(410, "PHONE_OTP_EXPIRED", "验证码已过期或已使用，请重新获取。")
    challenge.attempts += 1
    namespace = "phone-otp" if purpose == "login" else f"phone-otp:{purpose}"
    expected = credential_hash(settings.session_secret, namespace, code.strip())
    if challenge.attempts > 5 or not secrets.compare_digest(challenge.code_hash, expected):
        session.commit()
        raise ApiError(401, "PHONE_OTP_INVALID", "验证码不正确，请使用当前操作收到的验证码。")
    challenge.consumed_at = utc_now()
    return challenge


def encrypt_completion_code(code: str) -> str:
    settings = get_settings()
    key = hashlib.sha256(f"completion-code:{settings.session_secret}".encode()).digest()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, code.encode(), None)
    return base64.urlsafe_b64encode(nonce + encrypted).decode()


def decrypt_completion_code(ciphertext: str) -> str:
    settings = get_settings()
    key = hashlib.sha256(f"completion-code:{settings.session_secret}".encode()).digest()
    payload = base64.urlsafe_b64decode(ciphertext.encode())
    return AESGCM(key).decrypt(payload[:12], payload[12:], None).decode()


def issue_learner_session(
    session: Session,
    response: Response,
    *,
    identity: ExternalIdentity,
    request_id: str,
    audit_action: str = "phone.login_succeeded",
) -> tuple[str, object]:
    settings = get_settings()
    now = utc_now()
    for previous in session.scalars(
        select(IdentitySession)
        .where(
            IdentitySession.user_id == identity.user_id,
            IdentitySession.role == Role.LEARNER,
            IdentitySession.revoked_at.is_(None),
        )
        .with_for_update()
    ).all():
        previous.revoked_at = now
    session_token = random_token()
    csrf_token = random_token()
    expires_at = now + timedelta(hours=settings.learner_session_ttl_hours)
    identity_session = IdentitySession(
        id=uuid.uuid4(),
        organization_id=identity.organization_id,
        user_id=identity.user_id,
        external_identity_id=identity.id,
        external_identity_revision=identity.revision,
        role=Role.LEARNER,
        token_hash=credential_hash(settings.session_secret, "session", session_token),
        csrf_token_hash=credential_hash(settings.session_secret, "csrf", csrf_token),
        expires_at=expires_at,
    )
    session.add(identity_session)
    add_audit(
        session,
        request_id=request_id,
        organization_id=identity.organization_id,
        actor_id=identity.user_id,
        action=audit_action,
        resource_type="identity_session",
        resource_id=identity_session.id,
        result="SUCCESS",
        details={"provider": identity.provider, "entry_role": Role.LEARNER.value},
    )
    set_session_cookies(
        response,
        session_token,
        csrf_token,
        max_age=settings.learner_session_ttl_hours * 3600,
    )
    return csrf_token, expires_at


@router.post("/auth/password/login")
def login_with_password(
    command: PhonePasswordLogin,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.password_login_enabled:
        raise ApiError(503, "PASSWORD_LOGIN_DISABLED", "手机号密码登录尚未启用。")
    enforce_auth_limit(
        request,
        scope="password.login",
        secret=settings.session_secret,
        limit=10,
        message="登录尝试次数过多，请稍后再试。",
    )
    phone = normalized_phone(command.phone)
    password = validate_password(command.password)
    subject = phone_subject(phone)
    organization_id = lock_learner_organization(session)
    identity = password_phone_identity(session, subject)
    if identity is not None:
        if identity.revoked_at is not None:
            raise ApiError(409, "ACCOUNT_MIGRATED", "该账号已完成迁移，请使用企业飞书登录。")
        credential = session.scalar(
            select(PhonePasswordCredential).where(
                PhonePasswordCredential.external_identity_id == identity.id
            ).with_for_update()
        )
        if credential is None or not verify_password(
            password, credential.password_salt, credential.password_hash
        ):
            raise ApiError(401, "PHONE_OR_PASSWORD_INVALID", "手机号或密码不正确。")
        identity = provision_learner(
            session,
            identity,
            subject=subject,
            name="探索者",
            organization_id=organization_id,
            request_id=request.state.request_id,
            provider="PHONE_PASSWORD",
        )
    else:
        raise ApiError(401, "PHONE_OR_PASSWORD_INVALID", "手机号或密码不正确，首次使用请先注册。")
    remember_verified_phone(identity, phone)
    csrf_token, expires_at = issue_learner_session(
        session,
        response,
        identity=identity,
        request_id=request.state.request_id,
        audit_action="password.login_succeeded",
    )
    session.commit()
    return envelope(
        request,
        {
            "safe_entry": "/app",
            "expires_at": expires_at,
            "csrf_token": csrf_token,
            "display_name": "探索者",
            "is_new_user": False,
        },
    )


def verified_password_change(
    command: VerifiedPhonePassword, request: Request, response: Response,
    session: Session, *, purpose: Literal["register", "reset"],
):
    settings = get_settings()
    if not settings.password_login_enabled or not settings.phone_otp_enabled:
        raise ApiError(503, "PASSWORD_LOGIN_DISABLED", "手机注册及密码重置尚未启用。")
    enforce_auth_limit(request, scope="password.verify", secret=settings.session_secret,
                       limit=10, message="验证尝试次数过多，请稍后再试。")
    phone = normalized_phone(command.phone)
    password = validate_password(command.password)
    subject = phone_subject(phone)
    organization_id = lock_learner_organization(session)
    consume_phone_code(session, subject, command.code, purpose)
    identity = password_phone_identity(session, subject)
    if purpose == "register" and identity is not None:
        raise ApiError(409, "PHONE_ALREADY_REGISTERED", "该手机号已注册，请登录或找回密码。")
    if purpose == "reset" and identity is None:
        raise ApiError(404, "PHONE_NOT_REGISTERED", "该手机号尚未注册，请先注册账号。")
    identity = provision_learner(
        session, identity, subject=subject, name="探索者",
        organization_id=organization_id, request_id=request.state.request_id,
        provider="PHONE_PASSWORD",
    )
    session.flush()
    # Older SMS/nickname accounts keep the same identity, user and journey.
    if identity.provider != "PHONE_PASSWORD":
        identity.provider = "PHONE_PASSWORD"
        identity.revision += 1
    remember_verified_phone(identity, phone)
    credential = session.scalar(select(PhonePasswordCredential).where(
        PhonePasswordCredential.external_identity_id == identity.id,
    ).with_for_update())
    salt, digest = hash_password(password)
    if credential is None:
        credential = PhonePasswordCredential(
            id=uuid.uuid4(), external_identity_id=identity.id,
            password_salt=salt, password_hash=digest,
        )
        session.add(credential)
    else:
        credential.password_salt, credential.password_hash = salt, digest
    if purpose == "register":
        csrf_token, expires_at = issue_learner_session(
            session, response, identity=identity, request_id=request.state.request_id,
            audit_action="password.registration_succeeded",
        )
        session.commit()
        return envelope(request, {"safe_entry": "/app", "csrf_token": csrf_token,
                                  "expires_at": expires_at, "is_new_user": True})
    now = utc_now()
    for previous in session.scalars(select(IdentitySession).where(
        IdentitySession.user_id == identity.user_id,
        IdentitySession.revoked_at.is_(None),
    ).with_for_update()):
        previous.revoked_at = now
    add_audit(session, request_id=request.state.request_id,
              organization_id=identity.organization_id, actor_id=identity.user_id,
              action="password.reset_succeeded", resource_type="external_identity",
              resource_id=identity.id, result="SUCCESS", details={"provider": identity.provider})
    session.commit()
    return envelope(request, {"message": "密码已重置，请使用新密码登录。"})


@router.post("/auth/password/register")
def register_with_password(
    command: VerifiedPhonePassword, request: Request, response: Response,
    session: Session = Depends(get_db),
):
    return verified_password_change(command, request, response, session, purpose="register")


@router.post("/auth/password/reset")
def reset_password(
    command: VerifiedPhonePassword, request: Request, response: Response,
    session: Session = Depends(get_db),
):
    return verified_password_change(command, request, response, session, purpose="reset")


@router.post("/auth/phone/request-code")
def request_phone_code(
    command: RequestPhoneCode,
    request: Request,
    session: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.phone_otp_enabled:
        raise ApiError(503, "PHONE_LOGIN_DISABLED", "手机验证码登录尚未启用。")
    enforce_auth_limit(
        request,
        scope="phone.request-code",
        secret=settings.session_secret,
        limit=10,
        message="验证码获取次数过多，请稍后再试。",
    )
    phone = normalized_phone(command.phone)
    subject = phone_subject(phone)
    # This also serializes cooldown checks and sends for the same account.
    lock_learner_organization(session)
    if settings.password_login_enabled and command.purpose == "login":
        raise ApiError(409, "PASSWORD_LOGIN_REQUIRED", "请使用密码登录，或选择注册账号、忘记密码获取验证码。")
    if command.purpose != "login":
        if not settings.password_login_enabled:
            raise ApiError(503, "PASSWORD_LOGIN_DISABLED", "手机注册及密码重置尚未启用。")
        identity = password_phone_identity(session, subject)
        if command.purpose == "register" and identity is not None:
            raise ApiError(409, "PHONE_ALREADY_REGISTERED", "该手机号已注册，请登录或找回密码。")
        if command.purpose == "reset" and identity is None:
            raise ApiError(404, "PHONE_NOT_REGISTERED", "该手机号尚未注册，请先注册账号。")
    now = utc_now()
    previous_challenge = session.scalar(
        select(PhoneOtpChallenge)
        .where(PhoneOtpChallenge.phone_subject == subject)
        .order_by(PhoneOtpChallenge.created_at.desc())
    )
    if previous_challenge is not None:
        elapsed = (now - previous_challenge.created_at).total_seconds()
        if elapsed < settings.phone_otp_resend_cooldown_seconds:
            retry_after = max(1, int(settings.phone_otp_resend_cooldown_seconds - elapsed) + 1)
            raise ApiError(
                429,
                "PHONE_OTP_COOLDOWN",
                "验证码发送过于频繁，请稍后再试。",
                details={"retry_after_seconds": retry_after},
                retryable=True,
            )
    provider_message_id: str | None = None
    if settings.phone_otp_provider == "LOCAL_TEST":
        code = LOCAL_CODE
    elif settings.phone_otp_provider == "VOLCENGINE":
        code = f"{secrets.randbelow(1_000_000):06d}"
        client = VolcengineSmsClient(
            access_key_id=settings.volcengine_sms_access_key_id,
            secret_access_key=settings.volcengine_sms_secret_access_key,
            sms_account=settings.volcengine_sms_account,
            sign=settings.volcengine_sms_sign,
            template_id=settings.volcengine_sms_template_id,
            template_code_param=settings.volcengine_sms_template_code_param,
        )
        try:
            provider_message_id = client.send_code(
                phone,
                code,
                tag=request.state.request_id,
            )
        except SmsDeliveryError as error:
            raise ApiError(
                503,
                "SMS_DELIVERY_FAILED",
                "验证码发送失败，请稍后重试。",
                retryable=error.retryable,
            ) from error
    else:
        raise ApiError(503, "SMS_PROVIDER_NOT_CONFIGURED", "短信服务正在配置中。")
    challenge = PhoneOtpChallenge(
        id=uuid.uuid4(),
        phone_subject=subject,
        phone_last_four=phone[-4:],
        code_hash=credential_hash(settings.session_secret,
                                  "phone-otp" if command.purpose == "login" else f"phone-otp:{command.purpose}", code),
        attempts=0,
        expires_at=now + timedelta(minutes=settings.phone_otp_ttl_minutes),
    )
    session.add(challenge)
    add_audit(
        session,
        request_id=request.state.request_id,
        action="phone.otp_requested",
        resource_type="phone_otp_challenge",
        resource_id=challenge.id,
        result="SUCCESS",
        details={
            "phone_mask": f"*******{phone[-4:]}",
            "provider": settings.phone_otp_provider,
            "provider_message_id": provider_message_id,
            "purpose": command.purpose,
        },
    )
    session.commit()
    data: dict[str, object] = {
        "expires_in_seconds": settings.phone_otp_ttl_minutes * 60,
        "phone_mask": f"*******{phone[-4:]}",
        "retry_after_seconds": settings.phone_otp_resend_cooldown_seconds,
    }
    if settings.app_env in {"local", "test"} and settings.phone_otp_provider == "LOCAL_TEST":
        data["debug_code"] = LOCAL_CODE
    return envelope(request, data)


@router.post("/auth/phone/verify")
def verify_phone_code(
    command: VerifyPhoneCode,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.phone_otp_enabled:
        raise ApiError(503, "PHONE_LOGIN_DISABLED", "手机验证码登录尚未启用。")
    enforce_auth_limit(
        request,
        scope="phone.verify-code",
        secret=settings.session_secret,
        limit=20,
        message="验证码校验次数过多，请稍后再试。",
    )
    phone = normalized_phone(command.phone)
    subject = phone_subject(phone)
    if settings.password_login_enabled:
        raise ApiError(409, "PASSWORD_LOGIN_REQUIRED", "请使用密码登录，或先通过验证码注册、重置密码。")
    organization_id = lock_learner_organization(session)
    challenge = consume_phone_code(session, subject, command.code, "login")
    identity = session.scalar(
        select(ExternalIdentity)
        .where(ExternalIdentity.provider == "PHONE", ExternalIdentity.subject == subject)
        .with_for_update()
    )
    upgraded_from_nickname = False
    if identity is None:
        identity = session.scalar(
            select(ExternalIdentity)
            .where(
                ExternalIdentity.provider == "NICKNAME_PHONE",
                ExternalIdentity.subject == subject,
                ExternalIdentity.revoked_at.is_(None),
            )
            .with_for_update()
        )
        if identity is not None:
            identity.provider = "PHONE"
            identity.revision += 1
            upgraded_from_nickname = True
    identity = provision_learner(
        session,
        identity,
        subject=subject,
        name="探索者",
        organization_id=organization_id,
        request_id=request.state.request_id,
        provider="PHONE",
    )
    remember_verified_phone(identity, phone)
    # Keep a stable, privacy-preserving public identity for phone-only learners.
    # Once the journey is migrated to a Feishu account, that account keeps its
    # corporate display name instead.
    feishu_identity = session.scalar(
        select(ExternalIdentity.id).where(
            ExternalIdentity.user_id == identity.user_id,
            ExternalIdentity.organization_id == organization_id,
            ExternalIdentity.provider == "FEISHU",
            ExternalIdentity.revoked_at.is_(None),
        )
    )
    if feishu_identity is None and not upgraded_from_nickname:
        phone_user = session.scalar(
            select(User).where(User.id == identity.user_id).with_for_update()
        )
        if phone_user is not None and nickname_needed(session, phone_user):
            phone_user.display_name = "探索者"
    csrf_token, expires_at = issue_learner_session(
        session, response, identity=identity, request_id=request.state.request_id
    )
    session.commit()
    return envelope(
        request,
        {
            "safe_entry": "/app",
            "expires_at": expires_at,
            "csrf_token": csrf_token,
            "is_new_user": identity.verified_at >= challenge.created_at,
        },
    )


@router.get("/me/completion-code")
def get_completion_code(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
):
    settings = get_settings()
    require_role(actor, Role.LEARNER)
    temporary_identity = session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.user_id == actor.id,
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.provider.in_(TEMPORARY_IDENTITY_PROVIDERS),
            ExternalIdentity.revoked_at.is_(None),
        ).limit(1)
    )
    if temporary_identity is None:
        return envelope(request, {"status": "NOT_REQUIRED", "code": None})
    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.learner_id == actor.id,
            Enrollment.novice_task_id.is_(None),
            Enrollment.organization_id == actor.organization_id,
        )
        .order_by(Enrollment.id)
    )
    if enrollment is None:
        return envelope(request, {"status": "LOCKED", "completed": 0, "total": 0, "code": None})
    total, completed = session.execute(
        select(
            func.count(Assignment.id),
            func.count(Assignment.id).filter(Assignment.status == AssignmentStatus.COMPLETED),
        ).where(Assignment.enrollment_id == enrollment.id)
    ).one()
    if total == 0 or completed < total:
        return envelope(
            request,
            {"status": "LOCKED", "completed": completed, "total": total, "code": None},
        )
    row = session.scalar(
        select(CompletionCode).where(CompletionCode.user_id == actor.id).with_for_update()
    )
    if row is not None and row.used_at is not None:
        return envelope(request, {"status": "MIGRATED", "code": None})
    if row is None:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw_code = "MJ-" + "".join(secrets.choice(alphabet) for _ in range(8))
        row = CompletionCode(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            user_id=actor.id,
            code_hash=credential_hash(settings.session_secret, "completion-code", raw_code),
            code_ciphertext=encrypt_completion_code(raw_code),
            code_hint=raw_code[-4:],
            expires_at=utc_now() + timedelta(days=60),
        )
        session.add(row)
        session.commit()
    return envelope(
        request,
        {"status": "READY", "code": decrypt_completion_code(row.code_ciphertext), "expires_at": row.expires_at},
    )


@router.post("/me/completion-code/migrate")
def migrate_completion_code(
    command: MigrateCompletionCode,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
):
    require_role(actor, Role.LEARNER)
    settings = get_settings()
    feishu_identity = session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.user_id == actor.id,
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.provider == "FEISHU",
            ExternalIdentity.revoked_at.is_(None),
        )
    )
    if feishu_identity is None:
        raise ApiError(403, "FEISHU_ACCOUNT_REQUIRED", "请先使用公司飞书账号登录后再迁移。")
    # Serialize claims by the receiving corporate user as well as by code.
    target_user = session.scalar(select(User).where(User.id == actor.id).with_for_update())
    if target_user is None or target_user.status != UserStatus.ACTIVE:
        raise ApiError(401, "UNAUTHENTICATED", "当前飞书账号不可用。")
    raw_code = command.code.strip().upper()
    if not re.fullmatch(r"MJ-[A-Z2-9]{8}", raw_code):
        raise ApiError(422, "COMPLETION_CODE_INVALID", "探索营毕业码格式不正确。")
    row = session.scalar(
        select(CompletionCode)
        .where(CompletionCode.code_hash == credential_hash(settings.session_secret, "completion-code", raw_code))
        .with_for_update()
    )
    if row is None or row.expires_at <= utc_now():
        raise ApiError(404, "COMPLETION_CODE_INVALID", "探索营毕业码无效或已过期。")
    if row.used_at is not None:
        raise ApiError(409, "COMPLETION_CODE_USED", "该探索营毕业码已经使用。")
    if row.organization_id != actor.organization_id:
        raise ApiError(404, "COMPLETION_CODE_INVALID", "探索营毕业码无效或已过期。")
    if session.scalar(select(CompletionCode.id).where(
        CompletionCode.migrated_to_user_id == actor.id,
        CompletionCode.used_at.is_not(None),
    )) is not None:
        raise ApiError(409, "TARGET_ACCOUNT_HAS_PROGRESS", "公司飞书账号已有迁入的学习记录，请联系管理员合并。")
    source_user_id = row.user_id
    if source_user_id == actor.id:
        raise ApiError(409, "COMPLETION_CODE_SAME_ACCOUNT", "当前账号无需迁移。")
    temporary_identities = session.scalars(
        select(ExternalIdentity).where(
            ExternalIdentity.user_id == source_user_id,
            ExternalIdentity.provider.in_(TEMPORARY_IDENTITY_PROVIDERS),
            ExternalIdentity.revoked_at.is_(None),
        ).with_for_update()
    ).all()
    if not temporary_identities:
        raise ApiError(409, "COMPLETION_CODE_SOURCE_INVALID", "毕业码对应的临时账号不可迁移。")
    source_enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.learner_id == source_user_id,
            Enrollment.novice_task_id.is_(None),
            Enrollment.organization_id == actor.organization_id,
        ).with_for_update()
    )
    target_enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.learner_id == actor.id,
            Enrollment.novice_task_id.is_(None),
            Enrollment.organization_id == actor.organization_id,
        ).with_for_update()
    )
    if source_enrollment is None:
        raise ApiError(409, "COMPLETION_CODE_SOURCE_INVALID", "手机账号没有可迁移的探索营记录。")
    if target_enrollment is not None:
        has_target_activity = session.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.enrollment_id == target_enrollment.id,
                Assignment.status != AssignmentStatus.AVAILABLE,
            )
        ) or session.scalar(
            select(func.count(Submission.id)).join(Assignment, Assignment.id == Submission.assignment_id).where(
                Assignment.enrollment_id == target_enrollment.id
            )
        )
        has_target_activity = has_target_activity or session.scalar(
            select(LearningMaterialCompletion.id).where(
                LearningMaterialCompletion.enrollment_id == target_enrollment.id,
            ).limit(1)
        ) or session.scalar(select(SubmissionDraft.id).join(
            Assignment, Assignment.id == SubmissionDraft.assignment_id,
        ).where(Assignment.enrollment_id == target_enrollment.id).limit(1))
        if has_target_activity:
            raise ApiError(409, "TARGET_ACCOUNT_HAS_PROGRESS", "公司飞书账号已有学习记录，请联系管理员合并。")
    if actor.session_id is None:
        raise ApiError(401, "UNAUTHENTICATED", "当前飞书会话无效，请重新登录。")
    current_identity_session = session.scalar(
        select(IdentitySession)
        .where(IdentitySession.id == actor.session_id)
        .with_for_update()
    )
    if (
        current_identity_session is None
        or current_identity_session.external_identity_id != feishu_identity.id
    ):
        raise ApiError(401, "UNAUTHENTICATED", "当前飞书会话无效，请重新登录。")

    source_user = session.scalar(select(User).where(User.id == source_user_id).with_for_update())
    if source_user is None or source_user.organization_id != actor.organization_id or source_user.status != UserStatus.ACTIVE:
        raise ApiError(409, "COMPLETION_CODE_SOURCE_INVALID", "毕业码对应的账号不可迁移。")

    # Keep corporate identity, sessions, roles and review assignments unchanged.
    # The consumed code is the durable ownership link to immutable learner facts.
    now = utc_now()
    if session.scalar(select(RoleAssignment.id).where(
        RoleAssignment.user_id == source_user_id,
        RoleAssignment.role != Role.LEARNER,
    )) is not None or session.scalar(select(ExternalIdentity.id).where(
        ExternalIdentity.user_id == source_user_id,
        ExternalIdentity.provider.not_in(TEMPORARY_IDENTITY_PROVIDERS),
        ExternalIdentity.revoked_at.is_(None),
    )) is not None:
        raise ApiError(409, "COMPLETION_CODE_SOURCE_INVALID", "毕业码来源必须是尚未绑定企业身份的临时学员账号。")
    source_user.display_name = target_user.display_name
    source_user.status = UserStatus.DISABLED
    for phone_session in session.scalars(select(IdentitySession).where(
        IdentitySession.user_id == source_user_id,
        IdentitySession.revoked_at.is_(None),
    ).with_for_update()).all():
        phone_session.revoked_at = now
    # The phone identity has served its temporary purpose. Revoking it keeps
    # the migrated Feishu account authoritative and prevents later phone login
    # from changing the corporate display name.
    for temporary_identity in temporary_identities:
        temporary_identity.revoked_at = now
    row.used_at = now
    row.migrated_to_user_id = actor.id
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="completion_code.migrated",
        resource_type="completion_code",
        resource_id=row.id,
        result="SUCCESS",
        details={
            "source_user_id": str(source_user_id),
            "corporate_user_id": str(actor.id),
            "retired_phone_user_id": str(source_user_id),
        },
    )
    session.commit()
    return envelope(request, {"status": "MIGRATED", "migrated_tasks": session.scalar(
        select(func.count(Assignment.id)).where(Assignment.enrollment_id == source_enrollment.id)
    )})
