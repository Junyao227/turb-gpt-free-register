# -*- coding: utf-8 -*-
"""Small client for attaching Selenium to a local Ant Browser profile."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4

import requests

from config import ant_browser as _cfg


logger = logging.getLogger(__name__)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AntBrowserError(RuntimeError):
    """Raised when Ant Browser cannot provide a usable CDP endpoint."""


@dataclass(frozen=True)
class AntBrowserOpenResult:
    profile_id: str
    profile_name: str
    cdp_url: str
    debugger_address: str
    started_by_run: bool
    created_by_run: bool
    raw: dict

    def account_metadata(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "cdp_url": self.cdp_url,
            "started_by_run": self.started_by_run,
            "created_by_run": self.created_by_run,
        }


def _join_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _safe_text(value: object, *secrets: str) -> str:
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text[:300]


class AntBrowserClient:
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        api_key_header: str | None = None,
        profile_id: str | None = None,
        profile_mode: str | None = None,
        timeout: int | float | None = None,
        keep_browser_open: bool | None = None,
        delete_managed_profile: bool | None = None,
    ):
        self.api_base = str(api_base if api_base is not None else _cfg.ANT_BROWSER_API_BASE).strip().rstrip("/")
        self.api_key = str(api_key if api_key is not None else _cfg.ANT_BROWSER_API_KEY).strip()
        self.api_key_header = str(
            api_key_header if api_key_header is not None else _cfg.ANT_BROWSER_API_KEY_HEADER
        ).strip() or "X-Ant-Api-Key"
        self.profile_id = str(profile_id if profile_id is not None else _cfg.ANT_BROWSER_PROFILE_ID).strip()
        self.profile_mode = str(
            profile_mode if profile_mode is not None else _cfg.ANT_BROWSER_PROFILE_MODE
        ).strip().lower()
        self.timeout = max(1.0, float(timeout if timeout is not None else _cfg.ANT_BROWSER_START_TIMEOUT))
        self.keep_browser_open = bool(
            keep_browser_open if keep_browser_open is not None else _cfg.ANT_BROWSER_KEEP_BROWSER_OPEN
        )
        self.delete_managed_profile = bool(
            delete_managed_profile
            if delete_managed_profile is not None
            else _cfg.ANT_BROWSER_DELETE_MANAGED_PROFILE
        )
        self.http = requests.Session()
        self.http.headers.update({"Accept": "application/json"})
        if self.api_key:
            self.http.headers[self.api_key_header] = self.api_key

    def _require_profile_id(self) -> str:
        if not self.profile_id:
            raise AntBrowserError("ANT_BROWSER_PROFILE_ID is required")
        return self.profile_id

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        redactions: tuple[str, ...] = (),
    ) -> dict:
        if not self.api_base:
            raise AntBrowserError("ANT_BROWSER_API_BASE is required")
        url = _join_url(self.api_base, path)
        try:
            response = self.http.request(method, url, json=json_body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AntBrowserError(
                f"Ant Browser API request failed: {type(exc).__name__}: "
                f"{_safe_text(exc, self.api_key, *redactions)}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise AntBrowserError(
                f"Ant Browser API returned non-JSON response: HTTP {response.status_code}"
            ) from exc
        if not isinstance(payload, dict):
            raise AntBrowserError("Ant Browser API returned an invalid JSON object")
        if not response.ok or payload.get("ok") is False:
            message = _safe_text(
                payload.get("error") or payload.get("message") or "unknown error",
                self.api_key,
                *redactions,
            )
            raise AntBrowserError(f"Ant Browser API {method.upper()} {path} failed: HTTP {response.status_code}: {message}")
        return payload

    @staticmethod
    def _debugger_address(cdp_url: str) -> str:
        parsed = urlparse(str(cdp_url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.port:
            raise AntBrowserError("Ant Browser returned an invalid CDP URL")
        if parsed.username or parsed.password or parsed.hostname.lower() not in _LOOPBACK_HOSTS:
            raise AntBrowserError("Ant Browser CDP endpoint must use a local loopback address")
        return parsed.netloc

    @staticmethod
    def _endpoint_from_payload(payload: dict) -> str:
        direct_url = str(payload.get("directDebugUrl") or "").strip()
        if direct_url:
            return direct_url
        try:
            debug_port = int(payload.get("debugPort") or 0)
        except (TypeError, ValueError):
            debug_port = 0
        if debug_port > 0:
            return f"http://127.0.0.1:{debug_port}"
        return str(payload.get("cdpUrl") or "").strip()

    def _parse_open_result(
        self,
        payload: dict,
        *,
        started_by_run: bool,
        created_by_run: bool,
        expected_profile_id: str | None,
    ) -> AntBrowserOpenResult:
        profile_id = str(payload.get("profileId") or "").strip()
        if not profile_id:
            raise AntBrowserError("Ant Browser returned an empty profile ID")
        if expected_profile_id is not None and profile_id != expected_profile_id:
            raise AntBrowserError(
                f"Ant Browser returned profile {profile_id or '<empty>'!r}, expected {expected_profile_id!r}"
            )
        if not bool(payload.get("debugReady")):
            warning = _safe_text(payload.get("runtimeWarning") or payload.get("lastError"), self.api_key)
            suffix = f": {warning}" if warning else ""
            raise AntBrowserError(f"Ant Browser profile {profile_id} is not debug-ready{suffix}")
        cdp_url = self._endpoint_from_payload(payload)
        debugger_address = self._debugger_address(cdp_url)
        return AntBrowserOpenResult(
            profile_id=profile_id,
            profile_name=str(payload.get("profileName") or "").strip(),
            cdp_url=cdp_url,
            debugger_address=debugger_address,
            started_by_run=started_by_run,
            created_by_run=created_by_run,
            raw=payload,
        )

    def get_profile_status(self) -> dict:
        profile_id = quote(self._require_profile_id(), safe="")
        return self._request("GET", f"/api/profiles/{profile_id}/status")

    def _open_existing_profile(self) -> AntBrowserOpenResult:
        status = self.get_profile_status()
        if bool(status.get("running")):
            logger.info("[Ant Browser] Reusing running profile=%s", self.profile_id)
            return self._parse_open_result(
                status,
                started_by_run=False,
                created_by_run=False,
                expected_profile_id=self.profile_id,
            )

        logger.info("[Ant Browser] Starting profile=%s", self.profile_id)
        payload = self._request(
            "POST",
            "/api/launch",
            json_body={"profileId": self._require_profile_id()},
        )
        return self._parse_open_result(
            payload,
            started_by_run=True,
            created_by_run=False,
            expected_profile_id=self.profile_id,
        )

    @staticmethod
    def _created_profile_id(payload: dict) -> str:
        profile_id = str(payload.get("profileId") or "").strip()
        profile = payload.get("profile")
        if not profile_id and isinstance(profile, dict):
            profile_id = str(profile.get("profileId") or "").strip()
        if not profile_id:
            raise AntBrowserError("Ant Browser did not return the created profile ID")
        return profile_id

    def _create_managed_profile(self, proxy: str | None) -> str:
        proxy_config = str(proxy or "").strip()
        profile = {
            "profileName": f"gpt-registrar-{uuid4().hex[:12]}",
            "tags": ["gpt-registrar", "managed"],
        }
        if proxy_config:
            profile["proxyConfig"] = proxy_config
        else:
            profile["proxyId"] = "__direct__"
            profile["proxyConfig"] = "direct://"

        payload = self._request(
            "POST",
            "/api/profiles",
            json_body={"profile": profile},
            redactions=(proxy_config,),
        )
        return self._created_profile_id(payload)

    def _open_managed_profile(self, proxy: str | None) -> AntBrowserOpenResult:
        profile_id = self._create_managed_profile(proxy)
        logger.info("[Ant Browser] Starting managed profile=%s", profile_id)
        try:
            payload = self._request("POST", "/api/launch", json_body={"profileId": profile_id})
            return self._parse_open_result(
                payload,
                started_by_run=True,
                created_by_run=True,
                expected_profile_id=profile_id,
            )
        except Exception:
            self._cleanup_managed_profile(profile_id, may_be_running=True)
            raise

    def open_profile(self, proxy: str | None = None) -> AntBrowserOpenResult:
        if self.profile_mode == "existing":
            return self._open_existing_profile()
        if self.profile_mode == "managed":
            return self._open_managed_profile(proxy)
        raise AntBrowserError("ANT_BROWSER_PROFILE_MODE must be 'managed' or 'existing'")

    def build_driver(self, opened: AntBrowserOpenResult):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        logger.info("[Ant Browser] Connecting Selenium to profile=%s", opened.profile_id)
        options = Options()
        options.add_experimental_option("debuggerAddress", opened.debugger_address)
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(int(self.timeout))
        driver._registration_log_prefix = "[Ant Browser]"
        return driver

    def stop_profile(self, profile_id: str | None = None) -> None:
        target = quote(str(profile_id or self._require_profile_id()).strip(), safe="")
        self._request("POST", f"/api/profiles/{target}/stop")

    def delete_profile(self, profile_id: str) -> None:
        target_id = str(profile_id).strip()
        if not target_id:
            raise AntBrowserError("Ant Browser profile ID is required for deletion")
        target = quote(target_id, safe="")
        self._request("DELETE", f"/api/profiles/{target}")

    def _cleanup_managed_profile(self, profile_id: str, *, may_be_running: bool) -> None:
        if self.keep_browser_open:
            return
        if may_be_running:
            try:
                logger.info("[Ant Browser] Stopping managed profile=%s", profile_id)
                self.stop_profile(profile_id)
            except Exception as exc:
                logger.warning(
                    "[Ant Browser] Failed to stop managed profile=%s: %s",
                    profile_id,
                    _safe_text(exc, self.api_key),
                )
        if self.delete_managed_profile:
            try:
                logger.info("[Ant Browser] Deleting managed profile=%s", profile_id)
                self.delete_profile(profile_id)
            except Exception as exc:
                logger.warning(
                    "[Ant Browser] Failed to delete managed profile=%s: %s",
                    profile_id,
                    _safe_text(exc, self.api_key),
                )

    def cleanup_profile(self, opened: AntBrowserOpenResult | None) -> None:
        if not opened or self.keep_browser_open:
            return
        if opened.created_by_run:
            self._cleanup_managed_profile(opened.profile_id, may_be_running=opened.started_by_run)
            return
        if not opened.started_by_run:
            return
        try:
            logger.info("[Ant Browser] Stopping profile started by this run=%s", opened.profile_id)
            self.stop_profile(opened.profile_id)
        except Exception as exc:
            logger.warning("[Ant Browser] Failed to stop profile=%s: %s", opened.profile_id, _safe_text(exc, self.api_key))
