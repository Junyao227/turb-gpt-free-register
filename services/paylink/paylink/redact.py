from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


_SENSITIVE_KEY_RE = re.compile(r"(?:access[_-]?token|refresh[_-]?token|authorization|password|secret|proxy|claim[_-]?key|api[_-]?key)", re.I)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+\-/=]+")
_PROXY_CREDENTIAL_RE = re.compile(r"(?i)(?:https?|socks5?)://[^\s/@:]+(?::[^\s/@]*)?@")
_URL_SECRET_QUERY_RE = re.compile(r"(?i)([?&](?:access_token|refresh_token|authorization|password|secret|api_key)=)[^&#\s]+")


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _PROXY_CREDENTIAL_RE.sub(lambda match: match.group(0).split("://", 1)[0] + "://***@", text)
    return _URL_SECRET_QUERY_RE.sub(r"\1***", text)


def redact_value(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY_RE.search(str(key or "")):
        return "***"
    if isinstance(value, Mapping):
        return {str(item_key): redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
