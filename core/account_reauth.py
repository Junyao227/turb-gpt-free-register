# -*- coding: utf-8 -*-
"""Re-authenticate an existing ChatGPT account and obtain a fresh session token."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from core.account_export import fetch_session
from core.chatgpt_auth import get_csrf_token, get_providers, signin_openai
from core.openai_auth import (
    EmailOtpInvalidError,
    follow_authorize,
    network_preflight,
    send_email_otp,
    validate_email_otp,
)
from core.session import BrowserSession

logger = logging.getLogger(__name__)

_SUPPORTED_EMAIL_SOURCES = frozenset({"outlook", "generic_api"})


def _original_email_source(account: dict, email: str) -> str:
    """Resolve the persisted mailbox source without claiming a new mailbox."""
    declared = str(account.get("email_source") or "").strip().lower()
    if declared in _SUPPORTED_EMAIL_SOURCES:
        source = declared
    else:
        from core.email_provider import resolve_email_source

        source = resolve_email_source(email)
    if source not in _SUPPORTED_EMAIL_SOURCES:
        raise RuntimeError(
            f"账号邮箱来源为 {source or '未知'}，重新登录目前仅支持 Outlook 和 generic_api"
        )

    from core import db

    context = (
        db.get_generic_api_email_by_email(email)
        if source == "generic_api"
        else db.get_outlook_by_email(email)
    )
    if context is None:
        raise RuntimeError(f"账号原邮箱来源 {source} 中找不到邮箱配置，无法重新登录")
    return source


def _continue_url_from_otp(result: dict) -> str:
    page = result.get("page") if isinstance(result, dict) else {}
    page = page if isinstance(page, dict) else {}
    value = (
        result.get("continue_url")
        or result.get("external_url")
        or result.get("url")
        or page.get("continue_url")
        or page.get("external_url")
        or page.get("url")
    )
    return str(value or "").strip()


def _is_existing_account_callback(result: dict, continue_url: str) -> bool:
    page = result.get("page") if isinstance(result, dict) else {}
    page_type = str((page or {}).get("type") or "") if isinstance(page, dict) else ""
    if "about-you" in continue_url or page_type in {"about_you", "about-you"}:
        return False
    parsed = urlparse(continue_url)
    if parsed.netloc not in {"auth.openai.com", "chatgpt.com"}:
        return False
    return (
        page_type == "external_url"
        or "/authorize/continue" in parsed.path
        or "/api/auth/callback/" in parsed.path
    )


def _follow_callback_without_logging_url(session: BrowserSession, continue_url: str) -> None:
    """Finish OAuth without putting callback query values in the task log."""
    if continue_url.startswith("https://chatgpt.com"):
        headers = session.get_chatgpt_navigate_headers(
            referer="https://auth.openai.com/email-verification"
        )
    else:
        headers = session.get_auth_navigate_headers(
            referer="https://auth.openai.com/email-verification"
        )
    response = session.get(continue_url, headers=headers, allow_redirects=True)
    response.raise_for_status()


def run_account_reauth(
    email: str,
    *,
    account_id: int | None = None,
    proxy: str | None = None,
) -> dict:
    """Run the existing-account OTP login flow and return unsaved session data."""
    from core import db
    from config import openai_protocol as protocol_cfg

    email = str(email or "").strip()
    account = db.get_account(int(account_id)) if account_id is not None else (db.get_account_by_email(email) if email else None)
    if account is None:
        raise RuntimeError("账号不存在")
    stored_email = str(account.get("email") or "").strip()
    if not email:
        email = stored_email
    if stored_email.lower() != email.lower():
        raise RuntimeError("账号邮箱已发生变化，请刷新后重试")
    source = _original_email_source(account, email)
    logger.info("[重新登录] 开始：%s，邮箱来源=%s", email, source)

    session = BrowserSession(proxy=proxy)
    network_preflight(session)
    if getattr(protocol_cfg, "CHATGPT_ANON_BOOTSTRAP_ENABLED", True):
        from core.chatgpt_bootstrap import anonymous_bootstrap

        anonymous_bootstrap(
            session,
            strict=bool(getattr(protocol_cfg, "CHATGPT_BOOTSTRAP_STRICT", False)),
        )

    get_providers(session)
    csrf_token = get_csrf_token(session)
    authorize_url = signin_openai(session, csrf_token, email)
    otp_after_ts = time.time()
    follow_authorize(session, authorize_url)

    validate_result = None
    current_otp = None
    for attempt in range(1, 4):
        if current_otp is None:
            from core.email_provider import wait_for_otp

            logger.info("[重新登录] 等待邮箱验证码：%s（第 %s/3 次）", email, attempt)
            current_otp = wait_for_otp(email, after_ts=otp_after_ts)
        try:
            validate_result = validate_email_otp(session, current_otp)
            break
        except EmailOtpInvalidError:
            if attempt >= 3:
                raise
            logger.warning("[重新登录] 验证码无效或已过期，重新发送验证码")
            otp_after_ts = time.time()
            send_email_otp(session)
            current_otp = None

    if not isinstance(validate_result, dict):
        raise RuntimeError("重新登录 OTP 验证未完成")
    continue_url = _continue_url_from_otp(validate_result)
    if not _is_existing_account_callback(validate_result, continue_url):
        raise RuntimeError("登录流程未返回已有账号回调，已拒绝进入注册流程")

    _follow_callback_without_logging_url(session, continue_url)
    session_info = fetch_session(session)
    access_token = str(session_info.get("accessToken") or "").strip()
    if not access_token:
        raise RuntimeError("重新登录成功但未获取 access_token")

    logger.info("[重新登录] 已获取新的登录态：%s", email)
    return {
        "email": email,
        "email_source": source,
        "access_token": access_token,
        "session_info": session_info,
        "proxy_used": session.proxy or None,
        "device_id": session.device_id,
    }
