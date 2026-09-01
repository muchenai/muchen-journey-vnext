from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def canonical_document_sha256(document: dict[str, Any]) -> str:
    """Hash one contract object, excluding only its own root sha256 field."""

    def canonical_value(value: Any) -> Any:
        if isinstance(value, datetime):
            timestamp = value.astimezone(timezone.utc)
            return timestamp.isoformat().replace("+00:00", "Z")
        if isinstance(value, str) and (value.endswith("Z") or "+" in value[10:]):
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
            if timestamp.tzinfo is not None:
                return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(value, dict):
            return {str(key): canonical_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical_value(item) for item in value]
        return value

    payload = canonical_value(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
