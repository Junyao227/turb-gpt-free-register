# -*- coding: utf-8 -*-
"""ChatGPT OAuth token lifecycle helpers.

The registered-account record already has a top-level ``refresh_token`` for
the Outlook mailbox material.  ChatGPT OAuth credentials must therefore live
inside ``extra_json.chatgpt_oauth_tokens`` and never be inferred from mailbox
or Codex records.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping


logger = logging.getLogger(__name__)

TOKEN_STORAGE_KEY = "chatgpt_oauth_tokens"
TOKEN_VERSION = 1
DEFAULT_TOKEN_URL = "https://auth.openai.com/oauth/token"

STATUS_ACTIVE = "active"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: object) -> str:
    return str(value or "").strip()


def _expires_at(value: object, fallback: object = "") -> str:
    raw = _text(value) or _text(fallback)
    return raw


def _expires_from_seconds(value: object) -> str:
    try:
        seconds = max(0, int(value))
    except (TypeError, ValueError):
        return ""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _context_value(
    response: Mapping[str, Any],
    previous: Mapping[str, Any],
    context: Mapping[str, Any],
    name: str,
    default: str = "",
) -> str:
    response_context = response.get("oauth_context") or response.get("context") or {}
    response_context = response_context if isinstance(response_context, Mapping) else {}
    previous_context = previous.get("oauth_context") or {}
    previous_context = previous_context if isinstance(previous_context, Mapping) else {}
    return _text(
        context.get(name)
        or response_context.get(name)
        or response.get(name)
        or previous_context.get(name)
        or previous.get(name)
        or default
    )


def _has_refresh_context(tokens: Mapping[str, Any]) -> bool:
    context = tokens.get("oauth_context") if isinstance(tokens.get("oauth_context"), Mapping) else {}
    return bool(
        _text(tokens.get("refresh_token"))
        and _text(context.get("client_id"))
        and _text(context.get("redirect_uri"))
        and _text(context.get("token_url"))
    )


def redact_error(error: object) -> str:
    """Return a short diagnostic that cannot contain OAuth credentials."""
    text = _text(error) or "token refresh failed"
    text = re.sub(r"(?i)(access[_ -]?token|refresh[_ -]?token|id[_ -]?token|authorization|bearer|code_verifier|client_secret)\s*[:=]\s*[^,;\s]+", r"\1=[redacted]", text)
    text = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~-]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)(https?://[^\s\"'<>]+)\?[^\s\"'<>]+", r"\1?[redacted]", text)
    return text[:300]


def normalize_tokens(
    response: Mapping[str, Any] | None = None,
    *,
    previous: Mapping[str, Any] | None = None,
    fallback_access_token: object = "",
    session_expires_at: object = "",
    source: str = "registration",
    oauth_context: Mapping[str, Any] | None = None,
) -> dict:
    """Normalize a real ChatGPT OAuth response into the persisted structure.

    A browser ``/api/auth/session`` response has no OAuth refresh grant
    material.  Passing only ``fallback_access_token`` intentionally produces
    ``unavailable`` rather than manufacturing a refresh capability.
    """
    response = response if isinstance(response, Mapping) else {}
    previous = previous if isinstance(previous, Mapping) else {}
    oauth_context = oauth_context if isinstance(oauth_context, Mapping) else {}

    access_token = _text(response.get("access_token") or response.get("accessToken") or fallback_access_token or previous.get("access_token"))
    refresh_token = _text(response.get("refresh_token") or response.get("refreshToken") or previous.get("refresh_token"))
    id_token = _text(response.get("id_token") or response.get("idToken") or previous.get("id_token"))
    response_expires_at = _expires_at(response.get("expires_at") or response.get("expires"))
    if response_expires_at:
        expires_at = response_expires_at
    elif response.get("expires_in") is not None:
        expires_at = _expires_from_seconds(response.get("expires_in"))
    else:
        expires_at = _expires_at(session_expires_at, previous.get("expires_at"))

    context = {
        "client_id": _context_value(response, previous, oauth_context, "client_id"),
        "redirect_uri": _context_value(response, previous, oauth_context, "redirect_uri"),
        "token_url": _context_value(response, previous, oauth_context, "token_url", DEFAULT_TOKEN_URL),
    }
    tokens = {
        "version": TOKEN_VERSION,
        "source": _text(response.get("source") or source or previous.get("source")) or "registration",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "expires_at": expires_at,
        "last_refreshed_at": _text(previous.get("last_refreshed_at")),
        "status": STATUS_UNAVAILABLE,
        "last_error": "",
        "oauth_context": context,
    }
    previous_status = _text(previous.get("status"))
    is_persisted_lifecycle = bool(response.get("version") and "status" in response)
    if (not response or response == previous or is_persisted_lifecycle) and previous_status in {STATUS_FAILED, STATUS_UNAVAILABLE}:
        tokens["status"] = previous_status
        tokens["last_error"] = _text(previous.get("last_error"))
    elif _has_refresh_context(tokens):
        tokens["status"] = STATUS_ACTIVE
    return tokens


def preserve_after_session_reauth(
    previous: Mapping[str, Any] | None,
    *,
    access_token: object,
    expires_at: object = "",
) -> dict:
    """Keep a captured OAuth credential intact after a session-only reauth."""
    normalized = normalize_tokens(previous, previous=previous)
    if _has_refresh_context(normalized):
        return normalized
    return normalize_tokens(
        None,
        previous=normalized,
        fallback_access_token=access_token,
        session_expires_at=expires_at,
        source="reauth",
    )


def merge_refresh_response(previous: Mapping[str, Any], response: Mapping[str, Any]) -> dict:
    """Merge a successful refresh response, preserving an omitted rotation."""
    merged = normalize_tokens(response, previous=previous, source="manual_refresh")
    merged["source"] = "manual_refresh"
    merged["last_refreshed_at"] = _utc_now()
    merged["status"] = STATUS_ACTIVE if _has_refresh_context(merged) else STATUS_UNAVAILABLE
    merged["last_error"] = ""
    return merged


def mark_refresh_failure(previous: Mapping[str, Any], error: object) -> dict:
    """Record a safe refresh failure without discarding existing credentials."""
    tokens = normalize_tokens(previous, previous=previous)
    if _text(tokens.get("refresh_token")):
        tokens["status"] = STATUS_FAILED
    tokens["last_refreshed_at"] = _utc_now()
    tokens["last_error"] = redact_error(error)
    return tokens


def summarize_tokens(tokens: Mapping[str, Any] | None) -> dict:
    """Return only account-list-safe lifecycle metadata."""
    normalized = normalize_tokens(tokens, previous=tokens)
    return {
        "has_chatgpt_refresh_token": bool(_text(normalized.get("refresh_token"))),
        "can_refresh_chatgpt_token": _has_refresh_context(normalized),
        "chatgpt_token_refresh_status": normalized.get("status") or STATUS_UNAVAILABLE,
        "chatgpt_token_expires_at": normalized.get("expires_at") or "",
        "chatgpt_token_last_refreshed_at": normalized.get("last_refreshed_at") or "",
        "chatgpt_token_refresh_error": normalized.get("last_error") or "",
    }


@dataclass(frozen=True)
class RefreshGrantResult:
    ok: bool
    response: dict | None = None
    error: str = ""


def _default_post(
    url: str,
    data: dict[str, str],
    headers: dict[str, str],
    timeout: int,
    proxy: str | None,
):
    from curl_cffi import requests as cffi_requests

    session = cffi_requests.Session(impersonate="chrome", proxy=proxy or None)
    return session.post(url, data=data, headers=headers, timeout=timeout)


def refresh_with_stored_token(
    tokens: Mapping[str, Any] | None,
    *,
    proxy: str | None = None,
    post: Callable[[str, dict[str, str], dict[str, str], int, str | None], Any] | None = None,
) -> RefreshGrantResult:
    """Execute the OAuth refresh grant using only the stored ChatGPT context."""
    normalized = normalize_tokens(tokens, previous=tokens)
    if not _has_refresh_context(normalized):
        return RefreshGrantResult(False, error="account has no usable ChatGPT OAuth refresh token")

    context = normalized["oauth_context"]
    form = {
        "grant_type": "refresh_token",
        "refresh_token": normalized["refresh_token"],
        "client_id": context["client_id"],
        "redirect_uri": context["redirect_uri"],
    }
    post = post or _default_post
    try:
        response = post(
            context["token_url"],
            form,
            {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"},
            30,
            proxy,
        )
    except Exception as exc:
        return RefreshGrantResult(False, error=redact_error(f"token refresh network error: {type(exc).__name__}: {exc}"))

    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    if status_code != 200:
        code = _text(payload.get("error"))
        if isinstance(payload.get("error"), Mapping):
            code = _text(payload["error"].get("code") or payload["error"].get("error"))
        detail = f"token refresh rejected (HTTP {status_code or 'unknown'})"
        if code and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
            detail += f": {code}"
        return RefreshGrantResult(False, error=detail)
    if not _text(payload.get("access_token") or payload.get("accessToken")):
        return RefreshGrantResult(False, error="token refresh response is missing access_token")
    return RefreshGrantResult(True, response=payload)


def refresh_account(account_id: int, *, post: Callable[[str, dict[str, str], dict[str, str], int, str | None], Any] | None = None) -> dict:
    """Refresh one account and atomically persist its resulting token pair."""
    from core import db

    account = db.get_account(int(account_id))
    if account is None:
        return {"account_id": int(account_id), "status": "skipped", "error": "account not found"}
    tokens = db.get_chatgpt_oauth_tokens(int(account_id))
    normalized = normalize_tokens(tokens, previous=tokens)
    if not _has_refresh_context(normalized):
        return {"account_id": int(account_id), "status": "skipped", "error": "account has no usable ChatGPT OAuth refresh token"}

    result = refresh_with_stored_token(normalized, proxy=_text(account.get("proxy_used")) or None, post=post)
    expected_refresh_token = normalized["refresh_token"]
    if not result.ok:
        db.record_chatgpt_oauth_refresh_failure(int(account_id), expected_refresh_token, result.error)
        return {"account_id": int(account_id), "status": "failed", "error": result.error}

    if not db.apply_chatgpt_oauth_refresh_success(int(account_id), expected_refresh_token, result.response or {}):
        return {"account_id": int(account_id), "status": "skipped", "error": "token changed while refresh was in progress"}
    return {"account_id": int(account_id), "status": "refreshed", "error": ""}


def refresh_accounts(account_ids: list[int], *, post: Callable[[str, dict[str, str], dict[str, str], int, str | None], Any] | None = None) -> dict:
    """Refresh selected accounts and return a redacted aggregate result."""
    ids = []
    seen: set[int] = set()
    for value in account_ids:
        try:
            account_id = int(value)
        except (TypeError, ValueError):
            continue
        if account_id > 0 and account_id not in seen:
            seen.add(account_id)
            ids.append(account_id)

    results = [refresh_account(account_id, post=post) for account_id in ids]
    return {
        "requested_count": len(ids),
        "refreshed_count": sum(item["status"] == "refreshed" for item in results),
        "skipped_count": sum(item["status"] == "skipped" for item in results),
        "failed_count": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
