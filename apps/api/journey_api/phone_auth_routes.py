import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta

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
from journey_api.models import (
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


class VerifyPhoneCode(StrictModel):
    phone: str
    code: str


class PhonePasswordLogin(StrictModel):
    phone: str
    password: str


class MigrateCompletionCode(StrictModel):
    code: str


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


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
    identity = session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "PHONE_PASSWORD",
            ExternalIdentity.subject == subject,
        ).with_for_update()
    )
    is_new_user = identity is None
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
        identity = provision_learner(
            session,
            None,
            subject=subject,
            name="探索者",
            organization_id=organization_id,
            request_id=request.state.request_id,
            provider="PHONE_PASSWORD",
        )
        session.flush()
        password_salt, password_hash = hash_password(password)
        session.add(
            PhonePasswordCredential(
                id=uuid.uuid4(),
                external_identity_id=identity.id,
                password_salt=password_salt,
                password_hash=password_hash,
            )
        )
    csrf_token, expires_at = issue_learner_session(
        session,
        response,
        identity=identity,
        request_id=request.state.request_id,
        audit_action="password.registration_succeeded" if is_new_user else "password.login_succeeded",
    )
    session.commit()
    return envelope(
        request,
        {
            "safe_entry": "/app",
            "expires_at": expires_at,
            "csrf_token": csrf_token,
            "display_name": "探索者",
            "is_new_user": is_new_user,
        },
    )


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
        code_hash=credential_hash(settings.session_secret, "phone-otp", code),
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
        },
    )
    session.commit()
    data: dict[str, object] = {
        "expires_in_seconds": settings.phone_otp_ttl_minutes * 60,
        "phone_mask": f"*******{phone[-4:]}",
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
    challenge = session.scalar(
        select(PhoneOtpChallenge)
        .where(
            PhoneOtpChallenge.phone_subject == subject,
            PhoneOtpChallenge.consumed_at.is_(None),
        )
        .order_by(PhoneOtpChallenge.created_at.desc())
        .with_for_update()
    )
    if challenge is None or challenge.expires_at <= utc_now():
        raise ApiError(410, "PHONE_OTP_EXPIRED", "验证码已过期，请重新获取。")
    challenge.attempts += 1
    expected = credential_hash(settings.session_secret, "phone-otp", command.code.strip())
    if challenge.attempts > 5 or not secrets.compare_digest(challenge.code_hash, expected):
        session.commit()
        raise ApiError(401, "PHONE_OTP_INVALID", "验证码不正确。")
    challenge.consumed_at = utc_now()
    organization_id = lock_learner_organization(session)
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
        if phone_user is not None:
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
            Enrollment.organization_id == actor.organization_id,
        ).with_for_update()
    )
    target_enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.learner_id == actor.id,
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
