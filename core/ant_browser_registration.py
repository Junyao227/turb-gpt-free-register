# -*- coding: utf-8 -*-
"""Registration flow using an Ant Browser profile and Selenium CDP attach."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from config import ant_browser as _cfg
from config.proxy import pick_proxy
from config import twofa as _twofa_cfg
from core.account_export import save_account_data
from core.ant_browser_client import AntBrowserClient
from core.email_provider import resolve_email_source, wait_for_otp
from core.humanize import delay as human_delay
from core.roxy_registration import (
    _check_manual_stop,
    _clear_otp_inputs,
    _click_continue,
    _click_resend_email_otp,
    _complete_profile_page,
    _fetch_chatgpt_session,
    _fill_password_page_if_present,
    _maybe_accept,
    _submit_email_and_wait_next,
    _type_otp,
    _wait_after_email_otp_submit,
)


logger = logging.getLogger(__name__)


def run_ant_browser_registration(
    email: str,
    name: str,
    birthday: str,
    proxy: str = None,
    otp_code: str = None,
    batch_dir: Path | None = None,
) -> dict:
    """Run the maintained Selenium page flow inside an Ant Browser profile."""
    client = AntBrowserClient()
    opened = None
    driver = None
    create_acknowledged = False
    openai_password: str | None = None
    try:
        task_proxy = proxy if proxy is not None else pick_proxy()
        opened = client.open_profile(proxy=task_proxy)
        driver = client.build_driver(opened)
        logger.info("[Ant Browser] Registration start: email=%s profile=%s", email, opened.profile_id)

        otp_after_ts = time.time()
        driver.get(_cfg.ANT_BROWSER_START_URL)
        human_delay("navigate")
        _maybe_accept(driver)
        _check_manual_stop()

        next_state = _submit_email_and_wait_next(driver, email, attempts=3)
        _check_manual_stop()
        openai_password = None if next_state == "otp" else _fill_password_page_if_present(driver, email, timeout=25)
        _check_manual_stop()

        current_otp = otp_code
        max_otp_attempts = 3
        for otp_attempt in range(1, max_otp_attempts + 1):
            if current_otp is None:
                logger.info("[Ant Browser][OTP] Waiting for email=%s (%s/%s)", email, otp_attempt, max_otp_attempts)
                try:
                    current_otp = wait_for_otp(email, after_ts=otp_after_ts)
                except Exception as exc:
                    if otp_attempt >= max_otp_attempts:
                        raise
                    logger.warning("[Ant Browser][OTP] Waiting failed: %s: %s", type(exc).__name__, str(exc)[:180])
                    otp_after_ts = time.time()
                    _click_resend_email_otp(driver, timeout=25)
                    human_delay("api")
                    current_otp = None
                    continue
            _clear_otp_inputs(driver)
            _type_otp(driver, current_otp)
            _check_manual_stop()
            human_delay("otp_input")
            try:
                _click_continue(driver)
            except Exception as exc:
                logger.info("[Ant Browser][OTP] Continue button not found: %s", str(exc)[:120])

            if _wait_after_email_otp_submit(driver, timeout=10) == "accepted":
                break
            if otp_attempt >= max_otp_attempts:
                raise RuntimeError("Email OTP remained invalid or expired after all retry attempts")
            otp_after_ts = time.time()
            _click_resend_email_otp(driver, timeout=25)
            human_delay("api")
            current_otp = None

        profile_submitted = _complete_profile_page(driver, name, birthday, timeout=60)
        if profile_submitted:
            create_acknowledged = True
            human_delay("post_auth")

        _check_manual_stop()
        session_info = _fetch_chatgpt_session(driver, timeout=120)
        access_token = session_info["accessToken"]
        if _twofa_cfg.ENABLE_2FA:
            logger.warning("[Ant Browser] 2FA setup is not implemented for this driver; skipping")
        totp_secret = None

        codex_result = {
            "status": "skipped",
            "ok": True,
            "message": "Ant Browser Codex OAuth is not implemented",
        }
        account_id = save_account_data(
            email=email,
            access_token=access_token,
            totp_secret=totp_secret,
            email_source=resolve_email_source(email),
            proxy_used=f"ant-browser:{opened.profile_id}",
            batch_dir=batch_dir,
            extra={
                "user": session_info.get("user"),
                "account": session_info.get("account"),
                "expires": session_info.get("expires"),
                "ant_browser": opened.account_metadata(),
                "registration_password": openai_password,
                "codex": codex_result,
            },
        )
        return {
            "success": True,
            "email": email,
            "account_id": account_id,
            "access_token": access_token,
            "totp_secret": totp_secret,
            "codex": codex_result,
            "error": None,
        }
    except Exception as exc:
        logger.error("[Ant Browser] Registration failed: %s: %s", type(exc).__name__, exc)
        logger.debug("[Ant Browser] Registration failure details", exc_info=True)
        try:
            from core.email_provider import release_email
            release_email(
                email,
                status="failed" if create_acknowledged else "available",
                note=f"Ant Browser registration failed: {str(exc)[:180]}",
            )
        except Exception:
            pass
        return {"success": False, "email": email, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    finally:
        if driver and not bool(_cfg.ANT_BROWSER_KEEP_BROWSER_OPEN):
            try:
                driver.quit()
            except Exception:
                pass
        client.cleanup_profile(opened)
