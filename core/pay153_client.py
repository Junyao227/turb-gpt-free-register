# -*- coding: utf-8 -*-
"""Client adapter for the local PAY.153 protocol-payment service.

GPT Registrator keeps this as an integration boundary: configuration and
operator actions live here, while the PayPal Billing Agreement protocol flow
continues to be owned by the external PAY.153 project.
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any
from urllib.parse import quote

import requests

from config import pay153 as cfg


class Pay153Error(RuntimeError):
    """Base error returned by the PAY.153 adapter."""

    def __init__(self, message: str, *, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status


class Pay153ConfigError(Pay153Error):
    """Raised when the local PAY.153 integration is disabled or incomplete."""


_SESSION: requests.Session | None = None
_SESSION_LOCK = threading.RLock()

_BA_TOKEN_RE = re.compile(r"BA-[A-Za-z0-9]{8,80}")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:ba_token|token|ec_token|billingAgreementId|access_token|code|pin|password|otp)=)([^&\s\"']+)"
)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)(\b(?:ba_token|ec_token|billingAgreementId|token|accessToken|password|securityCode|cvv|pin|otp)\b\s*[:=]\s*)([\"']?)([^&,\"'\s}{]+)([\"']?)"
)
_PROXY_AUTH_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/@\s]+)@")


def _runtime_setting(name: str, default: Any = None) -> Any:
    try:
        from config.env_loader import load_env

        load_env(override=True)
    except Exception:
        pass
    raw = os.getenv(name)
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip()
    return getattr(cfg, name, default)


def _enabled() -> bool:
    value = _runtime_setting("PAY153_ENABLED", True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _timeout() -> int:
    try:
        value = int(_runtime_setting("PAY153_REQUEST_TIMEOUT", 30) or 30)
    except (TypeError, ValueError):
        value = 30
    return max(5, min(300, value))


def normalize_api_base(value: str | None = None) -> str:
    base = str(value if value is not None else _runtime_setting("PAY153_API_BASE", "") or "").strip().rstrip("/")
    if not base:
        raise Pay153ConfigError("PAY153_API_BASE 为空")
    lower = base.lower()
    if lower.endswith("/api"):
        return base
    if lower.endswith("/paypal-pay"):
        return f"{base}/api"
    return f"{base}/api"


def redact_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "")
    text = _BA_TOKEN_RE.sub("BA-***", text)
    text = _QUERY_SECRET_RE.sub(r"\1***", text)
    text = _KEY_VALUE_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(4)}", text)
    text = _PROXY_AUTH_RE.sub(r"\1***:***@", text)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _http_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def reset_session() -> None:
    """Reset the upstream cookie jar; useful for tests and manual recovery."""

    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is not None:
            try:
                _SESSION.close()
            except Exception:
                pass
        _SESSION = None


def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _enabled():
        raise Pay153ConfigError("PAY.153 协议支付集成已禁用")

    api_base = normalize_api_base()
    url = api_base + "/" + str(path or "").lstrip("/")
    try:
        with _SESSION_LOCK:
            response = _http_session().request(
                method.upper(),
                url,
                json=json_body,
                params=params,
                headers={"Accept": "application/json"},
                timeout=_timeout(),
            )
    except requests.RequestException as exc:
        raise Pay153Error(f"PAY.153 请求失败: {redact_text(exc)}") from exc

    try:
        data = response.json()
    except Exception:
        data = {"error": (response.text or "")[:500]}
    if not isinstance(data, dict):
        data = {"data": data}

    if response.status_code < 200 or response.status_code >= 300:
        message = data.get("error") or data.get("message") or f"PAY.153 HTTP {response.status_code}"
        raise Pay153Error(redact_text(message), upstream_status=response.status_code)
    return data


def health() -> dict[str, Any]:
    return _request("GET", "health")


def stats() -> dict[str, Any]:
    return _request("GET", "stats")


def supported_countries() -> dict[str, Any]:
    return _request("GET", "supported-countries")


def country_fields(country: str | None = None) -> dict[str, Any]:
    params = {"country": str(country or "").strip().upper()} if str(country or "").strip() else None
    return _request("GET", "country-fields", params=params)


def list_jobs() -> dict[str, Any]:
    return _request("GET", "jobs")


def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise Pay153ConfigError("PAY.153 创建任务请求体必须是 JSON 对象")

    allowed = {
        "ba_token",
        "paypal_url",
        "phone",
        "country",
        "paypal_country",
        "buyer_mode",
        "agreement_only",
        "proxies",
        "proxy_pool",
    }
    body = {key: value for key, value in payload.items() if key in allowed}
    body.setdefault("country", _runtime_setting("PAY153_DEFAULT_COUNTRY", "BR") or "BR")
    body.setdefault("buyer_mode", _runtime_setting("PAY153_DEFAULT_BUYER_MODE", "identity_elevation") or "identity_elevation")
    if "agreement_only" not in body:
        default_agreement_only = _runtime_setting("PAY153_DEFAULT_AGREEMENT_ONLY", False)
        if isinstance(default_agreement_only, bool):
            body["agreement_only"] = default_agreement_only
        else:
            body["agreement_only"] = str(default_agreement_only).strip().lower() in {"1", "true", "yes", "on", "y"}
    return _request("POST", "jobs", json_body=body)


def get_job(job_id: str, *, log_offset: int | None = None) -> dict[str, Any]:
    params = {"log_offset": int(log_offset)} if log_offset is not None else None
    return _request("GET", f"jobs/{quote(str(job_id or ''), safe='')}", params=params)


def submit_otp(job_id: str, value: str) -> dict[str, Any]:
    return _request("POST", f"jobs/{quote(str(job_id or ''), safe='')}/otp", json_body={"value": str(value or "").strip()})


def submit_captcha(job_id: str, value: str) -> dict[str, Any]:
    return _request("POST", f"jobs/{quote(str(job_id or ''), safe='')}/captcha", json_body={"value": str(value or "").strip()})


def browser_action(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise Pay153ConfigError("PAY.153 browser/action 请求体必须是 JSON 对象")
    return _request("POST", f"jobs/{quote(str(job_id or ''), safe='')}/browser/action", json_body=payload)


def cancel_job(job_id: str) -> dict[str, Any]:
    return _request("POST", f"jobs/{quote(str(job_id or ''), safe='')}/cancel", json_body={})
