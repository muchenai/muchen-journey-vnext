from types import SimpleNamespace

import pytest

from journey_api.attachments import ClamAvScanner, TosAttachmentStorage
from journey_api.config import get_settings
from journey_api.errors import ApiError


class FakeTosClient:
    def __init__(self) -> None:
        self.presign_calls: list[dict[str, object]] = []
        self.deleted: list[tuple[str, str]] = []

    def pre_signed_url(self, method, bucket, key, **kwargs):
        self.presign_calls.append(
            {"method": method.value, "bucket": bucket, "key": key, **kwargs}
        )
        return SimpleNamespace(
            signed_url=f"https://private.invalid/{key}?signed=redacted",
            signed_header={"host": "private.invalid", **kwargs.get("header", {})},
        )

    @staticmethod
    def head_object(bucket, key):
        return SimpleNamespace(
            content_length=12,
            content_type="text/plain",
            meta={"sha256": "a" * 64},
            etag="opaque-etag",
            version_id="opaque-version",
        )

    @staticmethod
    def get_object(bucket, key):
        return SimpleNamespace(content_length=12, read=lambda size: b"hello world\n")

    def delete_object(self, bucket, key):
        self.deleted.append((bucket, key))


class FakeClamConnection:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, _timeout):
        return None

    def sendall(self, content: bytes):
        self.sent.extend(content)

    def recv(self, _size: int) -> bytes:
        return self.response


@pytest.fixture(autouse=True)
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_tos_upload_is_object_scoped_short_lived_and_signed(monkeypatch):
    monkeypatch.setenv("ATTACHMENT_UPLOAD_TTL_SECONDS", "300")
    client = FakeTosClient()
    storage = TosAttachmentStorage(client=client, bucket="private-test")
    target = storage.presign_upload(
        storage_key="attachments/org/owner/object",
        local_upload_url="/unused",
        content_type="text/plain",
        sha256="a" * 64,
        filename="证据.txt",
    )
    assert target.url.startswith("https://private.invalid/attachments/org/owner/object?")
    assert "host" not in target.headers
    assert target.headers["x-tos-forbid-overwrite"] == "true"
    assert target.headers["x-tos-meta-sha256"] == "a" * 64
    assert target.headers["content-disposition"].startswith("attachment;")
    assert client.presign_calls[0]["expires"] == 300
    assert client.presign_calls[0]["is_signed_all_headers"] is True


def test_tos_completion_metadata_and_bounded_read():
    storage = TosAttachmentStorage(client=FakeTosClient(), bucket="private-test")
    stored = storage.head("attachments/org/owner/object")
    assert stored.size_bytes == 12
    assert stored.content_type == "text/plain"
    assert stored.sha256 == "a" * 64
    assert stored.etag == "opaque-etag"
    assert storage.get("attachments/org/owner/object") == b"hello world\n"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (b"stream: OK\0", True),
        (b"stream: Eicar-Test-Signature FOUND\0", False),
    ],
)
def test_clamav_scan_contract(monkeypatch, response, expected):
    connection = FakeClamConnection(response)
    monkeypatch.setattr(
        "journey_api.attachments.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )
    assert ClamAvScanner().scan(b"bounded sample") is expected
    assert connection.sent.startswith(b"zINSTREAM\0")
    assert connection.sent.endswith(b"\x00\x00\x00\x00")


def test_clamav_unavailable_fails_closed(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise TimeoutError("not exposed")

    monkeypatch.setattr(
        "journey_api.attachments.socket.create_connection", unavailable
    )
    with pytest.raises(ApiError) as error:
        ClamAvScanner().scan(b"bounded sample")
    assert error.value.status_code == 503
    assert error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert error.value.retryable is True
