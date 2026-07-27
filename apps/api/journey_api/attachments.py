from __future__ import annotations

import hashlib
import socket
import struct
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from journey_api.config import get_settings
from journey_api.errors import ApiError


MAX_ATTACHMENT_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "text/plain": {".txt"},
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
}


def safe_original_filename(value: str, content_type: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not normalized
        or len(normalized) > 180
        or normalized in {".", ".."}
        or normalized.startswith(".")
        or "/" in normalized
        or "\\" in normalized
        or any(unicodedata.category(char).startswith("C") for char in normalized)
    ):
        raise ApiError(422, "VALIDATION_FAILED", "附件文件名不安全，请重新命名后上传。")
    suffix = Path(normalized).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_TYPES.get(content_type, set()):
        raise ApiError(422, "VALIDATION_FAILED", "附件扩展名与内容类型不匹配。")
    return normalized


def validate_content(content: bytes, content_type: str) -> None:
    valid = False
    if content_type == "text/plain":
        try:
            content.decode("utf-8")
            valid = b"\x00" not in content
        except UnicodeDecodeError:
            valid = False
    elif content_type == "application/pdf":
        valid = content.startswith(b"%PDF-")
    elif content_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff")
    if not valid:
        raise ApiError(422, "VALIDATION_FAILED", "附件内容与声明的内容类型不匹配。")


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


def _valid_storage_key(storage_key: str) -> None:
    if not storage_key.startswith("attachments/") or ".." in storage_key:
        raise ApiError(500, "DEPENDENCY_UNAVAILABLE", "附件存储引用无效。")


@dataclass(frozen=True)
class UploadTarget:
    url: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True)
class StoredObject:
    size_bytes: int
    content_type: str | None
    sha256: str
    etag: str | None = None
    version_id: str | None = None


class AttachmentStorage(Protocol):
    supports_api_upload: bool

    def presign_upload(
        self,
        *,
        storage_key: str,
        local_upload_url: str,
        content_type: str,
        sha256: str,
        filename: str,
    ) -> UploadTarget: ...

    def put_from_api(self, storage_key: str, content: bytes) -> None: ...

    def head(self, storage_key: str) -> StoredObject: ...

    def get(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...

    def presign_download(self, storage_key: str) -> str | None: ...


class LocalAttachmentStorage:
    supports_api_upload = True

    def __init__(self) -> None:
        self.root = Path(get_settings().attachment_storage_root).resolve()

    def _path(self, storage_key: str) -> Path:
        _valid_storage_key(storage_key)
        path = (self.root / storage_key).resolve()
        if self.root not in path.parents:
            raise ApiError(500, "DEPENDENCY_UNAVAILABLE", "附件存储引用越界。")
        return path

    def presign_upload(
        self,
        *,
        storage_key: str,
        local_upload_url: str,
        content_type: str,
        sha256: str,
        filename: str,
    ) -> UploadTarget:
        _valid_storage_key(storage_key)
        settings = get_settings()
        return UploadTarget(
            url=local_upload_url,
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.attachment_upload_ttl_seconds),
        )

    def put_from_api(self, storage_key: str, content: bytes) -> None:
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".uploading")
        temporary.write_bytes(content)
        temporary.replace(path)

    def head(self, storage_key: str) -> StoredObject:
        content = self.get(storage_key)
        return StoredObject(
            size_bytes=len(content), content_type=None, sha256=digest_bytes(content)
        )

    def get(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise ApiError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "附件存储暂不可用，请稍后重试。",
                retryable=True,
            ) from exc
        if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
            raise ApiError(422, "VALIDATION_FAILED", "存储中的附件超过允许大小。")
        return content

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)

    def presign_download(self, storage_key: str) -> None:
        _valid_storage_key(storage_key)
        return None


class TosAttachmentStorage:
    supports_api_upload = False

    def __init__(self, client: object | None = None, bucket: str | None = None) -> None:
        if client is not None and bucket is not None:
            self.client = client
            self.bucket = bucket
            return
        settings = get_settings()
        try:
            from tos import EcsCredentialsProvider, TosClientV2
        except ImportError as exc:  # pragma: no cover - covered by container startup
            raise RuntimeError("TOS storage requires the pinned tos package") from exc
        provider = EcsCredentialsProvider(settings.tos_ecs_role_name)
        self.client = TosClientV2(
            endpoint=settings.tos_endpoint,
            region=settings.tos_region,
            credentials_provider=provider,
            max_retry_count=1,
            connection_time=3,
            socket_timeout=10,
        )
        self.bucket = settings.tos_bucket

    @staticmethod
    def _dependency_error(exc: Exception) -> ApiError:
        return ApiError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "附件对象存储暂不可用，请稍后重试。",
            retryable=True,
        )

    def presign_upload(
        self,
        *,
        storage_key: str,
        local_upload_url: str,
        content_type: str,
        sha256: str,
        filename: str,
    ) -> UploadTarget:
        _valid_storage_key(storage_key)
        settings = get_settings()
        headers = {
            "content-type": content_type,
            "content-disposition": download_disposition(filename),
            "x-tos-forbid-overwrite": "true",
            "x-tos-meta-sha256": sha256,
        }
        try:
            from tos.enum import HttpMethodType

            result = self.client.pre_signed_url(
                HttpMethodType.Http_Method_Put,
                self.bucket,
                storage_key,
                expires=settings.attachment_upload_ttl_seconds,
                header=headers,
                is_signed_all_headers=True,
            )
        except Exception as exc:
            raise self._dependency_error(exc) from exc
        browser_headers = {
            key: value
            for key, value in result.signed_header.items()
            if key.lower() != "host"
        }
        return UploadTarget(
            url=result.signed_url,
            headers=browser_headers,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.attachment_upload_ttl_seconds),
        )

    def put_from_api(self, storage_key: str, content: bytes) -> None:
        raise ApiError(404, "NOT_FOUND", "对象存储不接受经 API 转发的上传。")

    def head(self, storage_key: str) -> StoredObject:
        _valid_storage_key(storage_key)
        try:
            result = self.client.head_object(self.bucket, storage_key)
        except Exception as exc:
            raise self._dependency_error(exc) from exc
        return StoredObject(
            size_bytes=result.content_length,
            content_type=result.content_type,
            sha256=result.meta.get("sha256", ""),
            etag=result.etag,
            version_id=result.version_id,
        )

    def get(self, storage_key: str) -> bytes:
        _valid_storage_key(storage_key)
        try:
            result = self.client.get_object(self.bucket, storage_key)
            if result.content_length > MAX_ATTACHMENT_SIZE_BYTES:
                raise ApiError(422, "VALIDATION_FAILED", "存储中的附件超过允许大小。")
            content = result.read(MAX_ATTACHMENT_SIZE_BYTES + 1)
        except ApiError:
            raise
        except Exception as exc:
            raise self._dependency_error(exc) from exc
        if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
            raise ApiError(422, "VALIDATION_FAILED", "存储中的附件超过允许大小。")
        return content

    def delete(self, storage_key: str) -> None:
        _valid_storage_key(storage_key)
        try:
            self.client.delete_object(self.bucket, storage_key)
        except Exception as exc:
            raise self._dependency_error(exc) from exc

    def presign_download(self, storage_key: str) -> str:
        _valid_storage_key(storage_key)
        settings = get_settings()
        try:
            from tos.enum import HttpMethodType

            result = self.client.pre_signed_url(
                HttpMethodType.Http_Method_Get,
                self.bucket,
                storage_key,
                expires=settings.attachment_download_ttl_seconds,
            )
        except Exception as exc:
            raise self._dependency_error(exc) from exc
        return result.signed_url


@lru_cache
def get_attachment_storage() -> AttachmentStorage:
    if get_settings().attachment_storage_backend == "TOS":
        return TosAttachmentStorage()
    return LocalAttachmentStorage()


class AttachmentScanner(Protocol):
    def scan(self, content: bytes) -> bool: ...


class DeterministicTestScanner:
    def scan(self, content: bytes) -> bool:
        return b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" not in content


class ClamAvScanner:
    def scan(self, content: bytes) -> bool:
        settings = get_settings()
        try:
            with socket.create_connection(
                (settings.clamav_host, settings.clamav_port),
                timeout=settings.clamav_timeout_seconds,
            ) as connection:
                connection.settimeout(settings.clamav_timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 64 * 1024):
                    chunk = content[offset : offset + 64 * 1024]
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = bytearray()
                while len(response) < 4096 and b"\0" not in response:
                    chunk = connection.recv(4096 - len(response))
                    if not chunk:
                        break
                    response.extend(chunk)
        except (OSError, TimeoutError) as exc:
            raise ApiError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "附件安全扫描暂不可用，文件仍处于隔离状态。",
                retryable=True,
            ) from exc
        normalized = bytes(response).rstrip(b"\0\r\n")
        if normalized.endswith(b" OK"):
            return True
        if normalized.endswith(b" FOUND"):
            return False
        raise ApiError(
            503,
            "DEPENDENCY_UNAVAILABLE",
            "附件安全扫描返回无效结果，文件仍处于隔离状态。",
            retryable=True,
        )


@lru_cache
def get_attachment_scanner() -> AttachmentScanner:
    if get_settings().attachment_scanner_backend == "CLAMAV":
        return ClamAvScanner()
    return DeterministicTestScanner()
