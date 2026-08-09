from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse

ADMIN_SCOPE = "admin"
QR_SCOPE = "qr"
AUTH_COOKIE_NAME = "opll_auth"
AUTH_TTL_SECONDS = 48 * 60 * 60


def _normalize_scope(scope: str) -> str:
    return QR_SCOPE if str(scope or "").strip().lower() == QR_SCOPE else ADMIN_SCOPE


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _settings(secret_fallback: str = "") -> dict[str, str]:
    admin_password = os.getenv("OPLL_ADMIN_PASSWORD", "").strip()
    qr_password = os.getenv("OPLL_QR_PASSWORD", "").strip()
    signing_secret = os.getenv("OPLL_AUTH_SECRET", "").strip() or str(secret_fallback or "").strip()
    if (admin_password or qr_password) and not signing_secret:
        raise RuntimeError("auth is enabled but no signing secret is configured")
    return {
        "admin_password": admin_password,
        "qr_password": qr_password,
        "signing_secret": signing_secret,
    }


def auth_summary(secret_fallback: str = "") -> dict[str, Any]:
    settings = _settings(secret_fallback)
    return {
        "auth_enabled": bool(settings["admin_password"] or settings["qr_password"]),
        "admin_enabled": bool(settings["admin_password"]),
        "qr_enabled": bool(settings["qr_password"]),
        "ttl_seconds": AUTH_TTL_SECONDS,
    }


def _is_allowed(granted_scope: str, required_scope: str) -> bool:
    if granted_scope == ADMIN_SCOPE:
        return True
    return granted_scope == _normalize_scope(required_scope)


def _create_token(scope: str, secret_fallback: str = "") -> str:
    settings = _settings(secret_fallback)
    scope_value = _normalize_scope(scope)
    now_ts = int(time.time())
    payload = {
        "scope": scope_value,
        "iat": now_ts,
        "exp": now_ts + AUTH_TTL_SECONDS,
    }
    payload_text = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings["signing_secret"].encode("utf-8"),
        payload_text.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_text}.{_b64url_encode(signature)}"


def _read_token_payload(token: str, secret_fallback: str = "") -> dict[str, Any] | None:
    settings = _settings(secret_fallback)
    raw_token = str(token or "").strip()
    if not raw_token:
        return None
    try:
        payload_text, signature_text = raw_token.split(".", 1)
        expected_signature = hmac.new(
            settings["signing_secret"].encode("utf-8"),
            payload_text.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _b64url_decode(signature_text)
        if not hmac.compare_digest(actual_signature, expected_signature):
            return None
        payload = json.loads(_b64url_decode(payload_text).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    expires_at = int(payload.get("exp") or 0)
    if expires_at <= int(time.time()):
        return None
    return payload


def request_identity(request: Request, secret_fallback: str = "") -> dict[str, Any]:
    summary = auth_summary(secret_fallback)
    if not summary["auth_enabled"]:
        return {
            **summary,
            "authorized": True,
            "scope": ADMIN_SCOPE,
        }
    payload = _read_token_payload(request.cookies.get(AUTH_COOKIE_NAME, ""), secret_fallback)
    scope = _normalize_scope(str((payload or {}).get("scope") or ""))
    return {
        **summary,
        "authorized": payload is not None,
        "scope": scope if payload else "",
    }


def normalize_next_path(next_value: str, scope: str = ADMIN_SCOPE) -> str:
    raw_value = str(next_value or "").strip()
    if raw_value.startswith("/"):
        return raw_value
    return "/qr" if _normalize_scope(scope) == QR_SCOPE else "/"


def authenticate_scope(password: str, requested_scope: str, secret_fallback: str = "") -> str:
    settings = _settings(secret_fallback)
    requested = _normalize_scope(requested_scope)
    raw_password = str(password or "")
    if not (settings["admin_password"] or settings["qr_password"]):
        return ADMIN_SCOPE
    if not raw_password:
        raise HTTPException(status_code=400, detail="password is required")
    if settings["admin_password"] and hmac.compare_digest(raw_password, settings["admin_password"]):
        return ADMIN_SCOPE
    if settings["qr_password"] and hmac.compare_digest(raw_password, settings["qr_password"]):
        if requested == ADMIN_SCOPE:
            raise HTTPException(status_code=403, detail="admin password required")
        return QR_SCOPE
    raise HTTPException(status_code=401, detail="password incorrect")


def issue_auth_cookie(response: Response, scope: str, secret_fallback: str = "") -> None:
    token = _create_token(scope, secret_fallback)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


def require_api_scope(request: Request, required_scope: str, secret_fallback: str = "") -> None:
    identity = request_identity(request, secret_fallback)
    if not identity["auth_enabled"]:
        return
    if _is_allowed(str(identity["scope"] or ""), required_scope):
        return
    raise HTTPException(status_code=401, detail="auth required")


def require_page_scope(
    request: Request,
    required_scope: str,
    secret_fallback: str = "",
) -> RedirectResponse | None:
    identity = request_identity(request, secret_fallback)
    if not identity["auth_enabled"]:
        return None
    if _is_allowed(str(identity["scope"] or ""), required_scope):
        return None
    next_path = quote(str(request.url.path or "/"), safe="/?=&")
    login_url = f"/login?scope={_normalize_scope(required_scope)}&next={next_path}"
    return RedirectResponse(url=login_url, status_code=303)
