import base64
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import test_outcome_notifications_timeline as wp05
import test_reviewer_workbench as wp04
from journey_api.db import SessionLocal
from journey_api.models import (
    Assignment,
    AuditEntry,
    Enrollment,
    ExternalNotificationReceipt,
    NotificationChannel,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationEndpointStatus,
    NotificationStatus,
    OutboxEvent,
    OutboxStatus,
)
from journey_api.notification_recipients import decrypt_open_id, encrypt_open_id
from journey_worker.feishu import FeishuDeliveryError, FeishuReceipt, deliver
from journey_worker.main import WorkerSettings, process_batch


RECIPIENT_KEY = "bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4"
SYNTHETIC_APP_CREDENTIAL = "test-" + ("n" * 32)
ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self.payload = json.dumps(payload).encode()

    def read(self, _size: int) -> bytes:
        return self.payload


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, str, str, dict[str, str]]] = []
        self.closed = False

    def request(
        self, method: str, path: str, *, body: str, headers: dict[str, str]
    ) -> None:
        self.requests.append((method, path, body, headers))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_observability_contract_is_explicit_and_external_status_is_not_faked():
    contract = json.loads((ROOT / "config/wp11_observability.json").read_text())
    assert contract["external_collection"] == "NOT_RUN"
    assert contract["external_route"] == "UNCONFIGURED"
    assert contract["drill_evidence"] == "NOT_RUN"
    assert {
        "http_success_rate_by_route",
        "http_latency_by_route",
        "outbox_backlog",
        "oldest_pending_seconds",
        "notification_dead",
        "worker_heartbeat",
    }.issubset(contract["dashboard_contract"])
    forbidden = set(contract["log_source"]["forbidden_fields"])
    assert {"receive_id", "provider_message_id", "token", "submission_body"} <= forbidden
    dead_alert = next(
        alert
        for alert in contract["alert_contract"]
        if alert["name"] == "notification_dead_present"
    )
    assert dead_alert["detection_slo_minutes"] <= 240


def test_notification_recipient_encryption_is_scoped_and_tamper_evident():
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ciphertext, fingerprint = encrypt_open_id(
        "ou_learner_test_123",
        key_value=RECIPIENT_KEY,
        organization_id=organization_id,
        user_id=user_id,
    )
    assert "ou_learner_test_123" not in ciphertext
    assert len(fingerprint) == 64
    assert decrypt_open_id(
        ciphertext,
        key_value=RECIPIENT_KEY,
        organization_id=organization_id,
        user_id=user_id,
    ) == "ou_learner_test_123"
    with pytest.raises(ValueError, match="ciphertext is invalid"):
        decrypt_open_id(
            ciphertext,
            key_value=RECIPIENT_KEY,
            organization_id=organization_id,
            user_id=uuid.uuid4(),
        )
    version, encoded = ciphertext.split(".", maxsplit=1)
    blob = bytearray(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    blob[-1] ^= 1
    tampered = (
        f"{version}."
        f"{base64.urlsafe_b64encode(blob).decode('ascii').rstrip('=')}"
    )
    with pytest.raises(ValueError, match="ciphertext is invalid"):
        decrypt_open_id(
            tampered,
            key_value=RECIPIENT_KEY,
            organization_id=organization_id,
            user_id=user_id,
        )


def test_feishu_provider_uses_minimal_template_stable_uuid_and_safe_errors():
    token = FakeConnection(
        FakeResponse(200, {"code": 0, "tenant_access_token": "tenant-secret"})
    )
    message = FakeConnection(
        FakeResponse(200, {"code": 0, "data": {"message_id": "om_test"}})
    )
    connections = iter([token, message])
    receipt = deliver(
        app_id="cli_notification",
        app_secret=SYNTHETIC_APP_CREDENTIAL,
        receive_id="ou_learner_test_123",
        dedupe_key="notification:stable-dedupe",
        app_result_url="https://staging-vnext.muchenai.com/me/result",
        timeout_seconds=7,
        connection_factory=lambda timeout: next(connections),
    )
    assert receipt.message_id == "om_test"
    assert token.closed and message.closed
    method, path, body, headers = message.requests[0]
    assert method == "POST"
    assert path.startswith("/open-apis/im/v1/messages?receive_id_type=open_id&uuid=")
    assert headers["Authorization"] == "Bearer tenant-secret"
    request_body = json.loads(body)
    content = json.loads(request_body["content"])
    assert request_body["receive_id"] == "ou_learner_test_123"
    assert "https://staging-vnext.muchenai.com/me/result" in content["text"]
    for forbidden in ("decision", "feedback", "filename", "learner"):
        assert forbidden not in content["text"].lower()

    rate_limited = FakeConnection(FakeResponse(429, {"code": 230020}))
    with pytest.raises(FeishuDeliveryError) as error:
        deliver(
            app_id="cli_notification",
            app_secret=SYNTHETIC_APP_CREDENTIAL,
            receive_id="ou_learner_test_123",
            dedupe_key="notification:rate-limit",
            app_result_url="https://staging-vnext.muchenai.com/me/result",
            timeout_seconds=7,
            connection_factory=lambda timeout: rate_limited,
        )
    assert error.value.code == "FEISHU_RETRYABLE"
    assert error.value.retryable is True


def test_operator_endpoint_is_encrypted_audited_and_revocable(monkeypatch):
    flow = wp04.create_submission(f"wp11-endpoint-{uuid.uuid4()}")
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(flow["assignment_id"]))
        assert assignment is not None
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        assert enrollment is not None
        learner_id = enrollment.learner_id
    monkeypatch.setattr(
        "journey_api.ops_routes.get_settings",
        lambda: SimpleNamespace(
            notification_recipients_enabled=True,
            notification_recipient_key=RECIPIENT_KEY,
        ),
    )
    operator = wp04.client_for("wp11-operator")
    configured = wp04.assert_ok(
        operator.put(
            f"/api/v1/ops/users/{learner_id}/notification-endpoint",
            headers={
                **wp04.OPERATOR_HEADERS,
                "Idempotency-Key": f"wp11-endpoint-{uuid.uuid4()}",
            },
            json={
                "expected_revision": 0,
                "receive_id": "ou_learner_test_123",
                "reason": "为受控试点学员配置独立飞书通知接收人。",
            },
        )
    )
    assert set(configured) == {
        "id",
        "user_id",
        "channel",
        "receive_id_type",
        "status",
        "source",
        "revision",
        "updated_at",
        "idempotency_replay",
    }
    with SessionLocal() as session:
        endpoint = session.get(NotificationEndpoint, uuid.UUID(configured["id"]))
        assert endpoint is not None
        assert "ou_learner_test_123" not in endpoint.encrypted_receive_id
        assert decrypt_open_id(
            endpoint.encrypted_receive_id,
            key_value=RECIPIENT_KEY,
            organization_id=endpoint.organization_id,
            user_id=endpoint.user_id,
        ) == "ou_learner_test_123"
        audit = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "notification.endpoint.configured",
                AuditEntry.resource_id == endpoint.id,
            )
        )
        assert audit is not None
        assert "receive_id" not in json.dumps(audit.details)

    assert (
        wp04.client_for("wp11-reviewer").put(
            f"/api/v1/ops/users/{learner_id}/notification-endpoint",
            headers={
                **wp04.REVIEWER_HEADERS,
                "Idempotency-Key": f"wp11-denied-{uuid.uuid4()}",
            },
            json={
                "expected_revision": 1,
                "receive_id": "ou_attacker_test_123",
                "reason": "Reviewer 不得修改飞书通知接收人配置。",
            },
        ).status_code
        == 403
    )
    revoked = wp04.assert_ok(
        operator.post(
            f"/api/v1/ops/notification-endpoints/{configured['id']}/revoke",
            headers={
                **wp04.OPERATOR_HEADERS,
                "Idempotency-Key": f"wp11-revoke-{uuid.uuid4()}",
            },
            json={
                "expected_revision": 1,
                "reason": "试点接收人撤销后立即停止后续外部通知。",
            },
        )
    )
    assert revoked["status"] == "REVOKED"
    assert revoked["revision"] == 2
    with SessionLocal() as session:
        endpoint = session.get(NotificationEndpoint, uuid.UUID(configured["id"]))
        assert endpoint.status == NotificationEndpointStatus.REVOKED
        with pytest.raises(ValueError, match="ciphertext is invalid"):
            decrypt_open_id(
                endpoint.encrypted_receive_id,
                key_value=RECIPIENT_KEY,
                organization_id=endpoint.organization_id,
                user_id=endpoint.user_id,
            )


def test_dead_notification_manual_redrive_preserves_business_facts():
    flow = wp05.approve(f"wp11-redrive-{uuid.uuid4()}")
    outcome, _, delivery, event = wp05.notification_state(flow["evaluation_id"])
    for _ in range(2):
        failed = wp05.run_worker(event.id, behavior="always_fail", max_attempts=2)
        assert failed.returncode == 0, failed.stderr
        _, _, delivery, event = wp05.notification_state(flow["evaluation_id"])
    assert delivery.status == NotificationStatus.DEAD
    result_before = wp04.assert_ok(flow["learner"].get("/api/v1/me/result"))
    operator = wp04.client_for("wp11-redrive-operator")
    redriven = wp04.assert_ok(
        operator.post(
            f"/api/v1/ops/notification-deliveries/{delivery.id}/redrive",
            headers={
                **wp04.OPERATOR_HEADERS,
                "Idempotency-Key": f"wp11-redrive-{uuid.uuid4()}",
            },
            json={
                "expected_revision": 1,
                "reason": "本地适配器恢复后执行一次受控人工重驱验证。",
            },
        )
    )
    assert redriven["status"] == "PENDING"
    assert redriven["redrive_count"] == 1
    with SessionLocal() as session:
        current_delivery = session.get(NotificationDelivery, delivery.id)
        current_event = session.get(OutboxEvent, event.id)
        assert current_delivery.attempt_offset == 2
        assert current_event.status == OutboxStatus.PENDING
    succeeded = wp05.run_worker(event.id, behavior="success", max_attempts=2)
    assert succeeded.returncode == 0, succeeded.stderr
    _, _, delivery_after, _ = wp05.notification_state(flow["evaluation_id"])
    assert delivery_after.status == NotificationStatus.DELIVERED
    assert delivery_after.attempt_count == 3
    result_after = wp04.assert_ok(flow["learner"].get("/api/v1/me/result"))
    assert result_after["outcome_id"] == str(outcome.id)
    assert result_after["evaluation"] == result_before["evaluation"]
    assert result_after["handoff"] == result_before["handoff"]


def test_feishu_worker_records_one_private_receipt_without_changing_outcome(
    monkeypatch,
):
    flow = wp05.approve(f"wp11-feishu-{uuid.uuid4()}")
    outcome, _, delivery, event = wp05.notification_state(flow["evaluation_id"])
    with SessionLocal.begin() as session:
        stored_delivery = session.get(NotificationDelivery, delivery.id)
        stored_delivery.channel = NotificationChannel.FEISHU
        ciphertext, fingerprint = encrypt_open_id(
            "ou_learner_worker_123",
            key_value=RECIPIENT_KEY,
            organization_id=stored_delivery.organization_id,
            user_id=stored_delivery.recipient_user_id,
        )
        session.add(
            NotificationEndpoint(
                id=uuid.uuid4(),
                organization_id=stored_delivery.organization_id,
                user_id=stored_delivery.recipient_user_id,
                channel=NotificationChannel.FEISHU,
                receive_id_type="open_id",
                encrypted_receive_id=ciphertext,
                recipient_fingerprint=fingerprint,
                key_version=1,
                status=NotificationEndpointStatus.ACTIVE,
                source="OPERATOR_CONFIG",
                revision=1,
                created_by=stored_delivery.recipient_user_id,
            )
        )
    calls: list[dict[str, object]] = []

    def fake_deliver(**kwargs):
        calls.append(kwargs)
        return FeishuReceipt(message_id="om_private_provider_receipt")

    monkeypatch.setattr("journey_worker.main.deliver_feishu", fake_deliver)
    settings = WorkerSettings(
        app_env="staging",
        app_release="wp11-test",
        adapter="FEISHU",
        local_behavior="success",
        max_attempts=3,
        retry_base_seconds=0,
        lease_seconds=30,
        poll_seconds=1,
        crash_after_delivery=False,
        recipient_key=RECIPIENT_KEY,
        feishu_app_id="cli_notification",
        feishu_app_secret=SYNTHETIC_APP_CREDENTIAL,
        app_result_url="https://staging-vnext.muchenai.com/me/result",
        provider_timeout_seconds=7,
    )
    assert process_batch(event_id=event.id, settings=settings) == 1
    assert calls[0]["receive_id"] == "ou_learner_worker_123"
    with SessionLocal() as session:
        stored_delivery = session.get(NotificationDelivery, delivery.id)
        receipt = session.scalar(
            select(ExternalNotificationReceipt).where(
                ExternalNotificationReceipt.delivery_id == delivery.id
            )
        )
        assert stored_delivery.status == NotificationStatus.DELIVERED
        assert receipt.provider_message_id == "om_private_provider_receipt"
    result = wp04.assert_ok(flow["learner"].get("/api/v1/me/result"))
    assert result["outcome_id"] == str(outcome.id)
    assert result["notification"]["delivery_scope"] == "FEISHU"
    assert result["notification"]["external_delivery_confirmed"] is True
