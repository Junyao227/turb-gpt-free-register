from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import random
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from korea_qr import build_korea_qr_bundle, render_qr_svg
from paylink.redact import redact_text, redact_value
from page_auth import (
    ADMIN_SCOPE,
    QR_SCOPE,
    authenticate_scope,
    clear_auth_cookie,
    issue_auth_cookie,
    normalize_next_path,
    request_identity,
    require_api_scope,
    require_page_scope,
)
from pix_monitor import PixMonitor, PixMonitorConfig, PixMonitorDeps
from runtime_store import (
    append_log_event,
    clear_terminal_pix_pending_sessions,
    clear_terminal_provider_pending_sessions,
    ensure_runtime_dir as ensure_runtime_dir_path,
    get_pix_pending_session as load_pix_pending_session,
    get_provider_pending_session as load_provider_pending_session,
    list_log_events,
    list_pix_pending_sessions as load_pix_pending_sessions,
    list_provider_pending_sessions as load_provider_pending_sessions,
    load_task_snapshot_map,
    prune_task_snapshot_map,
    remove_provider_pending_session as delete_provider_pending_session,
    remove_task_snapshot,
    remove_pix_pending_session as delete_pix_pending_session,
    save_pix_pending_session as persist_pix_pending_session,
    save_provider_pending_session as persist_provider_pending_session,
    save_task_snapshot,
)

try:
    from curl_cffi.requests import Session as CurlCffiSession  # type: ignore
    from curl_cffi.requests.errors import RequestsError as CurlCffiRequestsError  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    CurlCffiSession = None  # type: ignore
    CurlCffiRequestsError = None  # type: ignore


logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover - Docker and local setup install python-dotenv
    pass

DEFAULT_STRIPE_PK = (
    "pk_live_51HOrSwC6h1nxGoI3lTAgRjYVrz4dU3fVOabyCcKR3pbEJguCVAlqCxdxCUvoRh1XWwRac"
    "ViovU3kLKvpkjh7IqkW00iXQsjo3n"
)
STRIPE_VERSION_FULL = "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1"
PROTOCOL_TRACE_HEADERS = ("x-request-id", "openai-request-id", "cf-ray")
DEFAULT_TIMEOUT = 30
PIX_STATUS_POLL_INTERVAL_SECONDS = 30
PIX_TERMINAL_DISPLAY_SECONDS = 3
PIX_QUEUE_LIMIT = 200
PIX_MONITOR_WORKER_COUNT = 4
MAX_CHECKOUT_PROXY_ATTEMPTS = 5
ZC_PICK_PAGE_SIZE = 500
BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
ASSET_DIR = PUBLIC_DIR / "assets"
RUNTIME_DIR = BASE_DIR / "runtime"
LOGIN_PAGE = PUBLIC_DIR / "login.html"
STATS_PAGE = PUBLIC_DIR / "stats.html"
DEBUG_GENERATE_PAGE = PUBLIC_DIR / "debug-generate.html"
UPI_PAGE = PUBLIC_DIR / "upi.html"
UPI_TASKS_PAGE = PUBLIC_DIR / "upi-tasks.html"
UPI_LOGS_PAGE = PUBLIC_DIR / "upi-logs.html"
UPI_RESULT_PAGE = PUBLIC_DIR / "upi-result.html"
KR_QR_PAGE = PUBLIC_DIR / "kr-qr.html"
CH_QR_PAGE = PUBLIC_DIR / "ch-qr.html"
IN_QR_PAGE = PUBLIC_DIR / "in-qr.html"
ID_QR_PAGE = PUBLIC_DIR / "id-qr.html"
NL_QR_PAGE = PUBLIC_DIR / "nl-qr.html"
ZC_DEFAULT_BASE_URL = os.getenv("OPLL_ZC_BASE_URL", "http://host.docker.internal:18001").strip()
ZC_DEFAULT_PASSWORD = os.getenv("OPLL_ZC_PASSWORD", "").strip()
ZC_DEFAULT_TOKEN = os.getenv("OPLL_ZC_TOKEN", "").strip()
ZC_DEFAULT_JWT_SECRET = os.getenv("OPLL_ZC_JWT_SECRET", "").strip()
ZC_DEFAULT_CLAIM_STATUS = os.getenv("OPLL_ZC_CLAIM_STATUS", "registered").strip()
DEFAULT_PROXY = os.getenv("OPENAI_PAY_DEFAULT_PROXY", "").strip()
PROVIDER_STAGE_PROXY = os.getenv("OPENAI_PAY_PROVIDER_PROXY", "").strip()
PIX_STAGE_PROXY = os.getenv("OPENAI_PAY_PIX_PROXY", "").strip()
PIX_PROMOTION_STAGE_PROXY = os.getenv("OPENAI_PAY_PIX_PROMOTION_PROXY", "").strip()
KOREA_STAGE_PROXY = os.getenv("OPENAI_PAY_KOREA_PROXY", "").strip()
SWISS_STAGE_PROXY = os.getenv("OPENAI_PAY_SWISS_PROXY", "").strip()
INDIA_STAGE_PROXY = os.getenv("OPENAI_PAY_INDIA_PROXY", "").strip()
UPI_SERVICE_TOKEN = os.getenv("OPENAI_PAY_UPI_SERVICE_TOKEN", "").strip()
UPI_BUSINESS_TOKEN = os.getenv("OPENAI_PAY_UPI_BUSINESS_TOKEN", "").strip()
UPI_FEATURE_ENABLED = os.getenv("OPENAI_PAY_UPI_FEATURE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
UPI_PHONE_ONLY = os.getenv("OPENAI_PAY_UPI_PHONE_ONLY", "0").strip().lower() in {"1", "true", "on", "yes"}
UPI_DEFAULT_POOL_KEEP = max(1, min(50, int(os.getenv("OPENAI_PAY_UPI_POOL_KEEP", "10") or 10)))
UPI_DEFAULT_POOL_MAX = max(1, min(2000, int(os.getenv("OPENAI_PAY_UPI_POOL_MAX", "200") or 200)))
UPI_SSE_PING_SECONDS = max(5, int(os.getenv("OPENAI_PAY_UPI_SSE_PING_SECONDS", "15") or 15))
GOPAY_PROVIDER_STAGE_PROXY = os.getenv("OPENAI_PAY_GOPAY_PROVIDER_PROXY", "").strip()
DEFAULT_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_DEFAULT_PROXY_POOL", "")
PROVIDER_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_PROVIDER_PROXY_POOL", "")
PIX_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_PIX_PROXY_POOL", "")
PIX_PROMOTION_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_PIX_PROMOTION_PROXY_POOL", "")
GOPAY_PROVIDER_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL", "")
KOREA_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_KOREA_PROXY_POOL", "")
SWISS_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_SWISS_PROXY_POOL", "")
INDIA_PROXY_POOL_RAW = os.getenv("OPENAI_PAY_INDIA_PROXY_POOL", "")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
DEFAULT_STRIPE_RUNTIME_VERSION = "6f8494a281"
PIX_PROMO_ID = "plus-1-month-free"
PIX_PROMOTION_REGION = "VN"
PIX_BILLING_COUNTRY = "BR"
PIX_BILLING_CURRENCY = "BRL"
PIX_BILLING_NAME = "Joao Silva"
PIX_BILLING_EMAIL = "buyer@example.com"
PIX_BILLING_LINE1 = "Avenida Paulista 1000"
PIX_BILLING_CITY = "Sao Paulo"
PIX_BILLING_POSTAL_CODE = "01310-100"
PIX_MAX_AMOUNT_CENTS = 50
PIX_REBUILD_ATTEMPTS = int(os.getenv("OPLL_PIX_REBUILD_ATTEMPTS", "5") or "5")
US_BILLING_NAMES = [
    ("James", "Smith"),
    ("John", "Brown"),
    ("Michael", "Johnson"),
    ("Robert", "Miller"),
    ("David", "Davis"),
    ("William", "Wilson"),
]
US_BILLING_STREETS = [
    ("3110 Sunset Boulevard", "Los Angeles", "CA", "90026"),
    ("1200 Market Street", "San Francisco", "CA", "94102"),
    ("500 Main Street", "Austin", "TX", "78701"),
    ("88 Broadway", "New York", "NY", "10007"),
    ("1200 Peachtree St", "Atlanta", "GA", "30309"),
]
JAPAN_BILLING_NAMES = [
    ("Taro", "Yamada"),
    ("Hanako", "Sato"),
    ("Ken", "Suzuki"),
    ("Yui", "Takahashi"),
    ("Haruto", "Tanaka"),
]
JAPAN_BILLING_STREETS = [
    ("1-2-3 Shibuya", "Shibuya-ku", "Tokyo", "150-0002"),
    ("2-1-1 Namba", "Chuo-ku", "Osaka", "542-0076"),
    ("3-4-5 Sakae", "Naka-ku", "Aichi", "460-0008"),
    ("4-2-8 Hakata", "Hakata-ku", "Fukuoka", "812-0011"),
]
INDONESIA_BILLING_NAMES = [
    ("Budi", "Santoso"),
    ("Agus", "Wijaya"),
    ("Siti", "Rahma"),
    ("Dewi", "Lestari"),
    ("Rizky", "Pratama"),
]
INDONESIA_BILLING_STREETS = [
    ("Jl. Jend. Sudirman No. 1", "Jakarta", "DKI Jakarta", "10210"),
    ("Jl. MH Thamrin No. 10", "Jakarta", "DKI Jakarta", "10350"),
    ("Jl. Asia Afrika No. 8", "Bandung", "Jawa Barat", "40111"),
    ("Jl. Basuki Rahmat No. 5", "Surabaya", "Jawa Timur", "60271"),
]
INDIA_BILLING_NAMES = [
    ("Aarav", "Sharma"),
    ("Vivaan", "Patel"),
    ("Ananya", "Gupta"),
    ("Diya", "Reddy"),
    ("Arjun", "Mehta"),
]
INDIA_BILLING_STREETS = [
    ("12 MG Road", "Bengaluru", "KA", "560001"),
    ("44 Linking Road", "Mumbai", "MH", "400050"),
    ("7 Park Street", "Kolkata", "WB", "700016"),
    ("18 Anna Salai", "Chennai", "TN", "600002"),
]
BRAZIL_BILLING_NAMES = [
    ("Joao", "Silva"),
    ("Maria", "Santos"),
    ("Pedro", "Oliveira"),
    ("Ana", "Souza"),
    ("Lucas", "Costa"),
]
BRAZIL_BILLING_STREETS = [
    ("Avenida Paulista 1000", "Sao Paulo", "SP", "01310-100"),
    ("Rua da Quitanda 86", "Rio de Janeiro", "RJ", "20091-005"),
    ("Avenida Afonso Pena 1500", "Belo Horizonte", "MG", "30130-005"),
    ("Avenida Sete de Setembro 2450", "Curitiba", "PR", "80230-010"),
]
PHILIPPINES_BILLING_NAMES = [
    ("Miguel", "Santos"),
    ("Andrea", "Reyes"),
    ("Paolo", "Garcia"),
    ("Angela", "Cruz"),
]
PHILIPPINES_BILLING_STREETS = [
    ("6750 Ayala Avenue", "Makati", "Metro Manila", "1226"),
    ("32nd Street", "Taguig", "Metro Manila", "1634"),
    ("Cebu Business Park", "Cebu City", "Cebu", "6000"),
    ("CM Recto Avenue", "Davao City", "Davao del Sur", "8000"),
]
COUNTRY_CURRENCY = {
    "AT": "EUR",
    "AU": "AUD",
    "BE": "EUR",
    "BR": "BRL",
    "CA": "CAD",
    "CH": "CHF",
    "CZ": "CZK",
    "DE": "EUR",
    "DK": "DKK",
    "ES": "EUR",
    "FI": "EUR",
    "FR": "EUR",
    "GB": "GBP",
    "HK": "HKD",
    "ID": "IDR",
    "IE": "EUR",
    "IN": "INR",
    "IT": "EUR",
    "JP": "JPY",
    "KR": "KRW",
    "MX": "MXN",
    "MY": "MYR",
    "NL": "EUR",
    "NO": "NOK",
    "NZ": "NZD",
    "PH": "PHP",
    "PL": "PLN",
    "PT": "EUR",
    "SE": "SEK",
    "SG": "SGD",
    "TH": "THB",
    "TW": "TWD",
    "US": "USD",
    "VN": "VND",
}
LOCALE_MAP = {
    "de": ("de-DE", "de"),
    "en": ("en-US", "en"),
    "en-PH": ("en-PH", "en"),
    "en-US": ("en-US", "en"),
    "es": ("es-ES", "es"),
    "fr": ("fr-FR", "fr"),
    "id": ("id-ID", "id"),
    "it": ("it-IT", "it"),
    "ja": ("ja-JP", "ja"),
    "ko": ("ko-KR", "ko"),
    "nl": ("nl-NL", "nl"),
    "pt-BR": ("pt-BR", "pt-BR"),
    "zh-CN": ("zh-CN", "zh-CN"),
    "zh-TW": ("zh-TW", "zh-TW"),
}
WALLET_APPROVAL_LINE_CONFIG = {
    "gopay": {
        "country": "ID",
        "payment_locale": "id",
        "timezone": "Asia/Jakarta",
        "proxy_region": "JP",
        "progress_label": "印度尼西亚 GoPay",
        "display_label": "GoPay",
    },
    "gcash": {
        "country": "PH",
        "payment_locale": "en-PH",
        "timezone": "Asia/Manila",
        "proxy_region": "PH",
        "progress_label": "菲律宾 GCash",
        "display_label": "GCash",
    },
    "grabpay": {
        "country": "PH",
        "payment_locale": "en-PH",
        "timezone": "Asia/Manila",
        "proxy_region": "PH",
        "progress_label": "菲律宾 GrabPay",
        "display_label": "GrabPay",
    },
}
FATAL_ACCOUNT_ERROR_CODES = {
    "token_invalidated",
    "account_deactivated",
    "access_token_invalid",
    "session_invalid",
    "http_401",
}
CHECKOUT_CHALLENGE_MARKERS = (
    "enable javascript and cookies to continue",
    "cf-mitigated",
    "__cf_chl",
    "enlarge-appear",
    "just a moment",
)


class LongLinkRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field("", alias="accessToken")
    proxy: str = ""
    stripe_publishable_key: str = ""
    billing_country: str = "US"
    checkout_ui_mode: str = "custom"
    payment_locale: str = "en"
    link_type: str = "hosted"
    use_promo_params: bool = True
    job_id: str = ""
    device_id: str = ""
    user_agent: str = ""
    buyer_tax_id: str = Field("", alias="buyerTaxId")
    auto_claim_zc: bool = Field(False, alias="autoClaimZc")
    zc_base_url: str = Field("", alias="zcBaseUrl")
    zc_token: str = Field("", alias="zcToken")
    zc_password: str = Field("", alias="zcPassword")
    zc_claim_status: str = Field("", alias="zcClaimStatus")
    zc_claim_key: str = Field("", alias="zcClaimKey")
    zc_claim_lease_seconds: int = Field(0, alias="zcClaimLeaseSeconds")
    concurrency: int = 1


class LongLinkResponse(BaseModel):
    ok: bool
    cs_id: str
    processor_entity: str
    checkout_url: str
    billing_country: str
    currency: str
    payment_locale: str
    link_type: str
    payment_method_type: str
    payment_method_id: str
    stripe_redirect_url: str
    provider_redirect_url: str
    fallback: bool = False
    provider_error: str = ""
    stripe_hosted_url: str
    long_url: str
    provider_qr_url: str = ""
    provider_qr_svg: str = ""
    provider_expires_at: int = 0
    next_action_type: str = ""
    upi_qr_data: str = ""
    upi_qr_image_url: str = ""
    upi_hosted_url: str = ""
    provider_ios_app_url: str = ""
    provider_aos_app_url: str = ""
    pix_hosted_instructions_url: str = ""
    pix_qr_code: str = ""
    pix_qr_image_url_png: str = ""
    pix_qr_image_url_svg: str = ""
    pix_expires_at: int = 0
    approval_result: str = ""
    submission_state: str = ""
    completion_stage: str = ""
    claimed_account_email: str = ""
    claimed_account_id: int = 0
    claimed_via_zc: bool = False
    claimed_claim_key: str = ""
    claimed_claim_expires_at: str = ""


class UpiApiRequest(BaseModel):
    token: str = ""
    promo_id: str = Field("plus-1-month-free", alias="promoId")
    pool_keep: int | None = Field(None, alias="poolKeep")
    pool_max: int | None = Field(None, alias="poolMax")


class UpiApiResponse(BaseModel):
    ok: bool
    reason: str
    retryable: bool | None = None
    message: str = ""
    next_action_type: str = ""
    upi_redirect_url: str = ""
    upi_qr_data: str = ""
    upi_qr_image_url: str = ""
    upi_hosted_url: str = ""
    request_id: str = ""
    duration_ms: int = 0


class ZCAccountsRequest(BaseModel):
    base_url: str = Field(..., alias="baseUrl")
    token: str = ""
    password: str = ""
    page_size: int = Field(100, alias="pageSize")
    status: str = ""
    has_rt: bool | None = Field(None, alias="hasRt")


class ZCAccountItem(BaseModel):
    id: int | None = None
    email: str = ""
    password: str = ""
    access_token: str = ""
    refresh_token: str = ""
    status: str = ""
    created_at: str = ""
    updated_at: str = ""
    token_source: str = ""


class ZCClaimRequest(BaseModel):
    base_url: str = Field("", alias="baseUrl")
    token: str = ""
    password: str = ""
    claim_key: str = Field(..., alias="claimKey")
    status: str = ""
    lease_seconds: int = Field(1800, alias="leaseSeconds")


class ZCReleaseRequest(BaseModel):
    base_url: str = Field(..., alias="baseUrl")
    token: str = ""
    password: str = ""
    claim_key: str = Field(..., alias="claimKey")
    account_id: int | None = Field(None, alias="accountId")


class PixStatusRequest(BaseModel):
    cs_id: str = Field(..., alias="csId")
    stripe_publishable_key: str = Field("", alias="stripePublishableKey")
    proxy: str = ""
    link_type: str = Field("pix", alias="linkType")
    user_agent: str = Field("", alias="userAgent")
    zc_base_url: str = Field("", alias="zcBaseUrl")
    zc_token: str = Field("", alias="zcToken")
    zc_password: str = Field("", alias="zcPassword")
    zc_claim_key: str = Field("", alias="zcClaimKey")
    claimed_account_id: int = Field(0, alias="claimedAccountId")
    claimed_account_email: str = Field("", alias="claimedAccountEmail")


class AuthLoginRequest(BaseModel):
    password: str = ""
    scope: str = ADMIN_SCOPE
    next: str = "/"


class TaskDeleteRequest(BaseModel):
    job_id: str = Field(..., alias="jobId")


def normalize_proxy_url(value: str, scheme: str = "http") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://", "socks5://", "socks5h://")):
        return raw

    match = re.match(r"^([^:/\s]+):(\d+):([^:]+):(.+)$", raw)
    if match:
        host, port, user, password = match.groups()
        return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"

    match = re.match(r"^([^:@\s]+):([^@\s]+)@([^:/\s]+):(\d+)$", raw)
    if match:
        user, password, host, port = match.groups()
        return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"

    match = re.match(r"^([^:/\s]+):(\d+)$", raw)
    if match:
        host, port = match.groups()
        return f"{scheme}://{host}:{port}"

    return raw


def parse_proxy_pool(raw: str) -> list[str]:
    parts = re.split(r"[\r\n,;]+", str(raw or "").strip())
    pool = [normalize_proxy_url(item) for item in parts if str(item).strip()]
    return [item for item in pool if item]


def rewrite_proxy_pool_region(pool: list[str], region: str) -> list[str]:
    return [proxy_for_region(item, region) for item in pool if str(item or "").strip()]


DEFAULT_PROXY_POOL = parse_proxy_pool(DEFAULT_PROXY_POOL_RAW)
PROVIDER_PROXY_POOL = parse_proxy_pool(PROVIDER_PROXY_POOL_RAW)
PIX_PROXY_POOL = parse_proxy_pool(PIX_PROXY_POOL_RAW)
PIX_PROMOTION_PROXY_POOL = parse_proxy_pool(PIX_PROMOTION_PROXY_POOL_RAW)
GOPAY_PROVIDER_PROXY_POOL = parse_proxy_pool(GOPAY_PROVIDER_PROXY_POOL_RAW)
KOREA_PROXY_POOL = parse_proxy_pool(KOREA_PROXY_POOL_RAW)
SWISS_PROXY_POOL = parse_proxy_pool(SWISS_PROXY_POOL_RAW)
INDIA_PROXY_POOL = parse_proxy_pool(INDIA_PROXY_POOL_RAW)
_proxy_cursor_lock = threading.Lock()
_proxy_cursor: dict[str, int] = {
    "default": 0,
    "provider": 0,
    "pix": 0,
    "pix_promotion": 0,
    "gopay": 0,
    "korea": 0,
    "swiss": 0,
    "upi": 0,
}
_stats_lock = threading.Lock()
_app_stats: dict[str, Any] = {
    "started_at": time.time(),
    "requests_total": 0,
    "success_total": 0,
    "paid_total": 0,
    "paid_failed_total": 0,
    "error_total": 0,
    "fallback_total": 0,
    "last_error": "",
    "last_success_at": 0.0,
}
_progress_lock = threading.Lock()
_pix_pending_lock = threading.Lock()
_pix_monitor: PixMonitor | None = None
ensure_runtime_dir_path(RUNTIME_DIR)
_progress_jobs: dict[str, dict[str, Any]] = load_task_snapshot_map(RUNTIME_DIR)


def next_proxy(pool_name: str, pool: list[str], fallback: str = "") -> str:
    if pool:
        with _proxy_cursor_lock:
            idx = _proxy_cursor.get(pool_name, 0)
            value = pool[idx % len(pool)]
            _proxy_cursor[pool_name] = (idx + 1) % len(pool)
        return value
    return normalize_proxy_url(fallback)


def bump_stats(
    *,
    request: bool = False,
    success: bool = False,
    paid: bool = False,
    paid_failed: bool = False,
    error: str = "",
    fallback: bool = False,
) -> None:
    with _stats_lock:
        if request:
            _app_stats["requests_total"] = int(_app_stats.get("requests_total") or 0) + 1
        if success:
            _app_stats["success_total"] = int(_app_stats.get("success_total") or 0) + 1
            _app_stats["last_success_at"] = time.time()
        if paid:
            _app_stats["paid_total"] = int(_app_stats.get("paid_total") or 0) + 1
        if paid_failed:
            _app_stats["paid_failed_total"] = int(_app_stats.get("paid_failed_total") or 0) + 1
        if fallback:
            _app_stats["fallback_total"] = int(_app_stats.get("fallback_total") or 0) + 1
        if error:
            _app_stats["error_total"] = int(_app_stats.get("error_total") or 0) + 1
            _app_stats["last_error"] = str(error)


def log_event(kind: str, message: str, **fields: Any) -> None:
    payload = {
        "ts": int(time.time()),
        "kind": str(kind or "").strip(),
        "message": redact_text(message).strip(),
    }
    for key, value in fields.items():
        sanitized = redact_value(value, key)
        if isinstance(sanitized, (dict, list)):
            text = json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
        else:
            text = str(sanitized or "").strip()
        if text:
            payload[key] = text
    append_log_event(RUNTIME_DIR, payload)


def event_field_text(value: Any, limit: int = 400) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
        text = text.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def payload_keys_text(payload: Any, limit: int = 8) -> str:
    if not isinstance(payload, dict):
        return "-"
    keys = [str(key) for key in sorted(payload.keys())[: max(1, int(limit or 8))]]
    return ",".join(keys) or "-"


STRIPE_CONFIRM_FIELD_LABELS = {
    "account_settings": "账号设置",
    "application": "应用",
    "approval_method": "审批方式",
    "automatic_payment_method_types": "自动支付方式",
    "beta_versions": "Beta版本",
    "billing_address_collection": "账单地址收集",
    "blob": "页面状态数据",
    "blocked_billing_address_countries": "禁止账单国家",
    "bnpl_in_link_ui_enabled": "Link分期入口",
    "bnpl_link_experiment_payment_method_type": "Link分期实验支付方式",
    "cancel_url": "取消地址",
    "capture_method": "扣款方式",
    "client_reference_id": "客户端引用ID",
    "currency": "币种",
    "customer": "客户",
    "line_items": "商品行项目",
    "livemode": "生产模式",
    "next_action": "下一步动作",
    "payment_intent": "PaymentIntent",
    "payment_method_collection": "支付方式收集",
    "payment_method_options": "支付方式配置",
    "payment_method_types": "支付方式列表",
    "return_url": "返回地址",
    "setup_intent": "SetupIntent",
    "shipping_address_collection": "收货地址收集",
    "shipping_options": "配送选项",
    "status": "会话状态",
    "submission_attempt": "提交结果",
    "success_url": "成功地址",
    "total_details": "金额明细",
}

STRIPE_CONFIRM_SUBMIT_LABELS = {
    "guid": "浏览器GUID",
    "muid": "设备MUID",
    "sid": "会话SID",
    "payment_method": "支付方式ID",
    "init_checksum": "初始化校验",
    "version": "Stripe版本",
    "expected_amount": "预期金额",
    "expected_payment_method_type": "预期支付方式",
    "return_url": "返回地址",
    "elements_session_client": "Elements会话",
    "elements_options_client": "Elements选项",
    "client_attribution_metadata": "客户端归因",
    "consent": "服务条款授权",
    "key": "Stripe公钥",
    "_stripe_version": "Stripe API版本",
}


def stripe_field_label(name: str) -> str:
    raw = str(name or "").split("[", 1)[0]
    return STRIPE_CONFIRM_FIELD_LABELS.get(raw) or STRIPE_CONFIRM_SUBMIT_LABELS.get(raw) or raw


def stripe_labels_text(names: Any, limit: int = 12) -> str:
    if isinstance(names, dict):
        raw_items = sorted(str(key) for key in names.keys())
    else:
        raw_items = [str(item) for item in names or []]
    labels: list[str] = []
    for item in raw_items:
        label = stripe_field_label(item)
        if label not in labels:
            labels.append(label)
        if len(labels) >= max(1, int(limit or 12)):
            break
    return "、".join(labels) or "无"


def protocol_response_headers_text(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    parts: list[str] = []
    for name in PROTOCOL_TRACE_HEADERS:
        value = str(headers.get(name) or "").strip()
        if value:
            parts.append(f"{name}={value}")
    return " ".join(parts)


def log_protocol_capture(
    kind: str,
    prefix: str,
    *,
    job_id: str = "",
    cs_id: str = "",
    status: str = "",
    response: Any | None = None,
    payload: Any = None,
    extras: tuple[str, ...] = (),
) -> None:
    parts = [prefix]
    if response is not None:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code:
            parts.append(f"http={status_code}")
        header_text = protocol_response_headers_text(response)
        if header_text:
            parts.append(header_text)
    if isinstance(payload, dict):
        parts.append(f"keys=[{payload_keys_text(payload)}]")
    parts.extend([text for text in extras if str(text or "").strip()])
    log_event(kind, " ".join(parts), job_id=job_id, cs_id=cs_id, status=status)


def log_stripe_confirm_success(
    response: Any,
    payload: Any,
    body: dict[str, Any],
    payment_method_type: str,
    *,
    job_id: str = "",
    cs_id: str = "",
) -> None:
    status_code = int(getattr(response, "status_code", 0) or 0)
    parts = ["Stripe confirm 成功"]
    if status_code:
        parts.append(f"HTTP状态={status_code}")
    parts.append(f"提交参数={stripe_labels_text(body, limit=18)}")
    parts.extend(confirm_payload_summary_cn(payload, payment_method_type))
    log_event("protocol.stripe_confirm", " ".join(parts), job_id=job_id, cs_id=cs_id, status="ok")


def confirm_payload_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "submission=- next_action=- redirect=0 setup_intent=-"
    submission = payload.get("submission_attempt") if isinstance(payload, dict) else None
    submission_state = str((submission or {}).get("state") or "").strip() or "-"
    next_action = payload.get("next_action") if isinstance(payload, dict) else None
    next_action_type = str((next_action or {}).get("type") or "").strip() or "-"
    has_redirect = "1" if extract_redirect_to_url(payload) else "0"
    setup_intent = find_setup_intent(payload) if isinstance(payload, dict) else None
    setup_intent_id = str((setup_intent or {}).get("id") or "").strip() or "-"
    return f"submission={submission_state} next_action={next_action_type} redirect={has_redirect} setup_intent={setup_intent_id}"


def payment_page_terminal_failure(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    submission = payload.get("submission_attempt")
    if not isinstance(submission, dict):
        return ""
    state = str(submission.get("state") or "").strip().lower()
    if state not in {"failed", "canceled", "expired"}:
        return ""
    error = submission.get("error")
    error_fields: list[str] = []
    if isinstance(error, dict):
        for key in ("code", "decline_code", "type", "message"):
            value = event_field_text(error.get(key), limit=160)
            if value:
                error_fields.append(f"{key}={value}")
        payment_error = error.get("payment_error")
        if isinstance(payment_error, dict):
            for key in ("code", "decline_code", "type", "message"):
                value = event_field_text(payment_error.get(key), limit=160)
                if value:
                    error_fields.append(f"payment_error.{key}={value}")
    suffix = " ".join(error_fields) or "reason=unknown"
    return redact_text(f"state={state} {suffix}")


def confirm_payload_summary_cn(payload: Any, payment_method_type: str) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return (
            f"支付方式={payment_method_type or '-'}",
            "响应体=不是 JSON 对象",
        )
    submission = payload.get("submission_attempt")
    next_action = payload.get("next_action")
    setup_intent = find_setup_intent(payload)
    redirect_url = extract_redirect_to_url(payload)
    submission_state = str((submission or {}).get("state") or "").strip() or "无"
    next_action_type = str((next_action or {}).get("type") or "").strip() or "无"
    setup_intent_id = str((setup_intent or {}).get("id") or "").strip() or "无"
    redirect_state = "有" if redirect_url else "无"
    return (
        f"支付方式={payment_method_type or '-'}",
        f"提交状态={submission_state}",
        f"下一步动作={next_action_type}",
        f"跳转链接={redirect_state}",
        f"SetupIntent={setup_intent_id}",
        f"响应字段={stripe_labels_text(payload, limit=18)}",
    )


def app_stats_snapshot() -> dict[str, Any]:
    with _stats_lock:
        data = dict(_app_stats)
    task_items = list_progress_jobs(limit=500)
    pix_items = list_pix_pending_sessions(limit=PIX_QUEUE_LIMIT)
    log_items = list_log_events(RUNTIME_DIR, limit=2000)
    paid_total = len([item for item in log_items if str(item.get("kind") or "") == "pix.paid"])
    paid_failed_total = len([item for item in log_items if str(item.get("kind") or "") == "pix.failed"])
    task_running = len([item for item in task_items if not item.get("done")])
    task_done = len([item for item in task_items if item.get("done") and not item.get("error")])
    task_failed = len([item for item in task_items if item.get("error")])
    pix_succeeded = len([item for item in pix_items if str(item.get("state") or "").strip().lower() == "succeeded"])
    pix_terminal = len(
        [item for item in pix_items if str(item.get("state") or "").strip().lower() in {"failed", "expired", "canceled"}]
    )
    started_at = float(data.get("started_at") or time.time())
    uptime_seconds = max(0, int(time.time() - started_at))
    return {
        "ok": True,
        "uptime_seconds": uptime_seconds,
        "requests_total": int(data.get("requests_total") or 0),
        "success_total": int(data.get("success_total") or 0),
        "paid_total": paid_total,
        "paid_failed_total": paid_failed_total,
        "error_total": int(data.get("error_total") or 0),
        "fallback_total": int(data.get("fallback_total") or 0),
        "last_error": str(data.get("last_error") or ""),
        "last_success_at": float(data.get("last_success_at") or 0.0),
        "default_proxy_pool_size": len(DEFAULT_PROXY_POOL) or (1 if DEFAULT_PROXY else 0),
        "provider_proxy_pool_size": len(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL) or (1 if PROVIDER_STAGE_PROXY or DEFAULT_PROXY else 0),
        "gopay_proxy_pool_size": len(GOPAY_PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL) or (1 if GOPAY_PROVIDER_STAGE_PROXY or DEFAULT_PROXY else 0),
        "promo_enabled_default": True,
        "task_running_total": task_running,
        "task_done_total": task_done,
        "task_failed_total": task_failed,
        "pix_queue_total": len(pix_items),
        "pix_succeeded_total": pix_succeeded,
        "pix_terminal_total": pix_terminal,
        "log_total": len(log_items),
    }


def progress_job_id(raw: str = "") -> str:
    text = re.sub(r"[^A-Za-z0-9_-]", "", str(raw or "").strip())
    return text[:80] if text else uuid.uuid4().hex


def set_progress(
    job_id: str,
    *,
    percent: int,
    text: str,
    done: bool = False,
    error: bool = False,
    result: dict[str, Any] | None = None,
) -> None:
    global _progress_jobs
    if not job_id:
        return
    with _progress_lock:
        existing = _progress_jobs.get(job_id) or {}
        snapshot = {
            "ok": True,
            "job_id": job_id,
            "percent": max(0, min(100, int(percent))),
            "text": redact_text(text),
            "done": bool(done),
            "error": bool(error),
            "created_at": float(existing.get("created_at") or time.time()),
            "updated_at": time.time(),
        }
        if result is not None:
            snapshot["result"] = redact_value(result)
        elif isinstance(existing.get("result"), dict):
            snapshot["result"] = existing["result"]
        saved_snapshot = save_task_snapshot(RUNTIME_DIR, snapshot)
        updated = dict(_progress_jobs)
        updated[job_id] = saved_snapshot
        _progress_jobs = prune_task_snapshot_map(updated)
    previous_text = str(existing.get("text") or "")
    if str(snapshot.get("text") or "") != previous_text or bool(snapshot.get("done")) != bool(existing.get("done")):
        task_state = "failed" if error else ("done" if done else "running")
        log_event("task.progress", str(text or task_state), job_id=job_id, status=task_state)


def refresh_progress_cache() -> None:
    global _progress_jobs
    _progress_jobs = load_task_snapshot_map(RUNTIME_DIR)


def get_progress(job_id: str) -> dict[str, Any]:
    global _progress_jobs
    if not job_id:
        return {"ok": False, "detail": "job_id is required"}
    with _progress_lock:
        if job_id not in _progress_jobs:
            refresh_progress_cache()
        snapshot = dict(_progress_jobs.get(job_id) or {"ok": False, "detail": "job not found"})
    failure_reason = progress_snapshot_failure_reason(snapshot)
    if not failure_reason:
        return snapshot
    snapshot["error"] = True
    snapshot["text"] = failure_reason
    return snapshot


def get_progress_many(job_ids: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in job_ids:
        job_id = progress_job_id(raw)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        items.append(get_progress(job_id))
    return items


def _normalize_progress_job_items(items: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        done = 1 if bool(item.get("done")) else 0
        updated_at = float(item.get("updated_at") or 0.0)
        return (done, -updated_at)

    items.sort(key=sort_key)
    normalized: list[dict[str, Any]] = []
    bounded_items = items
    if limit is not None:
        bounded_items = items[: max(1, min(int(limit or 50), 200))]
    for item in bounded_items:
        failure_reason = progress_snapshot_failure_reason(item)
        is_error = bool(item.get("error")) or bool(failure_reason)
        text = str(failure_reason or item.get("text") or "")
        status = "failed" if is_error else ("done" if item.get("done") else "running")
        normalized.append(
            {
                "ok": True,
                "job_id": str(item.get("job_id") or ""),
                "status": status,
                "percent": int(item.get("percent") or 0),
                "text": text,
                "done": bool(item.get("done")),
                "error": is_error,
                "created_at": float(item.get("created_at") or 0.0),
                "updated_at": float(item.get("updated_at") or 0.0),
                "result": item.get("result") if isinstance(item.get("result"), dict) else None,
            }
        )
    return normalized


def list_progress_jobs(limit: int = 50) -> list[dict[str, Any]]:
    global _progress_jobs
    with _progress_lock:
        refresh_progress_cache()
        items = [dict(item) for item in _progress_jobs.values()]
    return _normalize_progress_job_items(items, limit=limit)


def list_progress_jobs_page(page: int = 1, page_size: int = 10) -> dict[str, Any]:
    global _progress_jobs
    with _progress_lock:
        refresh_progress_cache()
        items = [dict(item) for item in _progress_jobs.values()]
    normalized = _normalize_progress_job_items(items, limit=None)
    total = len(normalized)
    bounded_page_size = max(1, min(int(page_size or 10), 50))
    total_pages = max(1, (total + bounded_page_size - 1) // bounded_page_size)
    current_page = max(1, min(int(page or 1), total_pages))
    start = (current_page - 1) * bounded_page_size
    end = start + bounded_page_size
    summary = {
        "total": total,
        "running": len([item for item in normalized if not item.get("done")]),
        "done": len([item for item in normalized if item.get("done") and not item.get("error")]),
        "failed": len([item for item in normalized if item.get("error")]),
    }
    return {
        "items": normalized[start:end],
        "page": current_page,
        "page_size": bounded_page_size,
        "total": total,
        "total_pages": total_pages,
        "summary": summary,
    }


def delete_progress_job(job_id: str) -> bool:
    global _progress_jobs
    normalized_job_id = progress_job_id(job_id)
    if not normalized_job_id:
        return False
    with _progress_lock:
        removed = remove_task_snapshot(RUNTIME_DIR, normalized_job_id)
        if removed:
            updated = dict(_progress_jobs)
            updated.pop(normalized_job_id, None)
            _progress_jobs = prune_task_snapshot_map(updated)
    return removed


def list_task_log_events(job_id: str, limit: int = 200) -> list[dict[str, Any]]:
    normalized_job_id = progress_job_id(job_id)
    if not normalized_job_id:
        return []
    items = []
    for item in list_log_events(RUNTIME_DIR, limit=2000):
        if str(item.get("job_id") or "").strip() != normalized_job_id:
            continue
        normalized = dict(item)
        normalized["job_id"] = str(item.get("job_id") or "").strip()
        normalized["kind"] = str(item.get("kind") or "").strip()
        normalized["message"] = str(item.get("message") or "").strip()
        normalized["status"] = str(item.get("status") or "").strip()
        normalized["cs_id"] = str(item.get("cs_id") or "").strip()
        items.append(normalized)
    bounded = max(1, min(int(limit or 200), 500))
    return list(reversed(items[:bounded]))


def progress_error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        try:
            return json.dumps(detail, ensure_ascii=False)
        except Exception:
            return str(detail or exc.__class__.__name__)
    return str(exc) or exc.__class__.__name__


def _ensure_runtime_dir() -> None:
    ensure_runtime_dir_path(RUNTIME_DIR)


def save_pix_pending_session(session_data: dict[str, Any]) -> None:
    if not isinstance(session_data, dict):
        return
    with _pix_pending_lock:
        persist_pix_pending_session(RUNTIME_DIR, session_data)


def save_provider_pending_session(session_data: dict[str, Any]) -> None:
    if not isinstance(session_data, dict):
        return
    persist_provider_pending_session(RUNTIME_DIR, session_data)


def enrich_korea_provider_fields(
    provider_fields: dict[str, Any],
    req: LongLinkRequest,
    provider_proxy: str = "",
) -> dict[str, Any]:
    provider_url = str(provider_fields.get("provider_redirect_url") or "").strip()
    if not provider_url:
        return dict(provider_fields)
    qr_bundle = build_korea_qr_bundle(
        provider_url=provider_url,
        user_agent=req.user_agent.strip() or DEFAULT_USER_AGENT,
        proxy=provider_proxy,
        timeout_seconds=DEFAULT_TIMEOUT,
    )
    return {
        **provider_fields,
        "provider_qr_url": str(qr_bundle.get("qr_url") or ""),
        "provider_qr_svg": str(qr_bundle.get("qr_svg") or ""),
        "provider_expires_at": int(qr_bundle.get("expired_at") or 0),
        "provider_ios_app_url": str(qr_bundle.get("ios_app_url") or ""),
        "provider_aos_app_url": str(qr_bundle.get("aos_app_url") or ""),
        "provider_bridge_url": str(qr_bundle.get("bridge_url") or ""),
        "provider_status": str(qr_bundle.get("status") or ""),
        "provider_kakao_tid": str(qr_bundle.get("kakao_tid") or ""),
    }


def enrich_pix_session_from_tasks(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    enriched = dict(item)
    cs_id = str(enriched.get("csId") or "").strip()
    if not cs_id:
        return enriched
    for task in list_progress_jobs(limit=500):
        result = task.get("result") if isinstance(task.get("result"), dict) else None
        if not isinstance(result, dict):
            continue
        if str(result.get("cs_id") or "").strip() != cs_id:
            continue
        mapping = {
            "pix_qr_code": "pixQrCode",
            "pix_qr_image_url_png": "pixQrImageUrlPng",
            "pix_qr_image_url_svg": "pixQrImageUrlSvg",
            "pix_hosted_instructions_url": "pixHostedInstructionsUrl",
            "pix_expires_at": "pixExpiresAt",
        }
        changed = False
        for source_key, target_key in mapping.items():
            source_value = result.get(source_key)
            if enriched.get(target_key) or not source_value:
                continue
            enriched[target_key] = source_value
            changed = True
        if changed:
            save_pix_pending_session(enriched)
        return enriched
    return enriched


def pix_session_has_display_data(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(
        str(item.get("pixQrImageUrlPng") or "").strip()
        or str(item.get("pixQrCode") or "").strip()
        or str(item.get("pixHostedInstructionsUrl") or "").strip()
    )


def get_pix_pending_session(cs_id: str) -> dict[str, Any] | None:
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        return None
    with _pix_pending_lock:
        return load_pix_pending_session(RUNTIME_DIR, normalized_cs_id)


def remove_pix_pending_session(cs_id: str) -> None:
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        return
    with _pix_pending_lock:
        delete_pix_pending_session(RUNTIME_DIR, normalized_cs_id)


def list_pix_pending_sessions(limit: int = 20) -> list[dict[str, Any]]:
    with _pix_pending_lock:
        items = load_pix_pending_sessions(RUNTIME_DIR, limit=limit)
    enriched = [enrich_pix_session_from_tasks(item) for item in items]
    stale_cs_ids = [
        str(item.get("csId") or "").strip()
        for item in enriched
        if item and not pix_session_has_display_data(item)
    ]
    for cs_id in stale_cs_ids:
        if cs_id:
            remove_pix_pending_session(cs_id)
    return [item for item in enriched if pix_session_has_display_data(item)]


def provider_session_has_display_data(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(
        str(item.get("providerRedirectUrl") or "").strip()
        or str(item.get("paymentPageUrl") or "").strip()
        or str(item.get("longUrl") or "").strip()
        or str(item.get("qrUrl") or "").strip()
        or str(item.get("qrSvg") or "").strip()
    )


def list_provider_pending_sessions(link_type: str, limit: int = 20) -> list[dict[str, Any]]:
    items = load_provider_pending_sessions(RUNTIME_DIR, link_type, limit=limit)
    return [item for item in items if provider_session_has_display_data(item)]


def get_provider_pending_session(link_type: str, cs_id: str) -> dict[str, Any] | None:
    return load_provider_pending_session(RUNTIME_DIR, link_type, cs_id)


def remove_provider_pending_session(link_type: str, cs_id: str) -> bool:
    return delete_provider_pending_session(RUNTIME_DIR, link_type, cs_id)


def provider_page_path_for_link_type(link_type: str) -> str:
    normalized = normalize_link_type(link_type)
    if normalized == "korea":
        return "/kr-qr"
    if normalized == "swiss":
        return "/ch-qr"
    if normalized == "upi":
        return "/in-qr"
    if normalized == "ideal":
        return "/nl-qr"
    return "/qr"


def provider_generation_progress_text(link_type: str) -> str:
    normalized = normalize_link_type(link_type)
    if normalized == "korea":
        return "生成 KakaoPay 支付页"
    if normalized == "swiss":
        return "生成 Swiss 支付页"
    if normalized == "upi":
        return "生成 India UPI 二维码"
    if normalized == "ideal":
        return "生成荷兰 iDEAL 支付页"
    if normalized in WALLET_APPROVAL_LINE_CONFIG:
        return f"提交 {WALLET_APPROVAL_LINE_CONFIG[normalized]['progress_label']} 支付"
    return "生成 provider 支付信息"


def current_timestamp() -> int:
    return int(time.time())


def wallet_approval_line_config(link_type: str) -> dict[str, str]:
    normalized = normalize_link_type(link_type)
    return WALLET_APPROVAL_LINE_CONFIG.get(normalized, {})


def wallet_result_requires_provider_redirect(link_type: str) -> bool:
    normalized = normalize_link_type(link_type)
    return normalized in WALLET_APPROVAL_LINE_CONFIG or normalized == "ideal"


def result_provider_display_ready(result: dict[str, Any]) -> bool:
    return bool(
        str(result.get("provider_redirect_url") or "").strip()
        or str(result.get("long_url") or "").strip()
        or str(result.get("upi_hosted_url") or "").strip()
        or str(result.get("pix_hosted_instructions_url") or "").strip()
    )


def progress_snapshot_failure_reason(snapshot: dict[str, Any]) -> str:
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    link_type = normalize_link_type(result.get("link_type") or "")
    if not result or not wallet_result_requires_provider_redirect(link_type):
        return ""
    approval_result = str(result.get("approval_result") or "").strip().lower()
    if approval_result and approval_result != "approved":
        return f"{link_type} approval did not succeed: {approval_result}"
    if approval_result == "approved" and not result_provider_display_ready(result):
        return f"{link_type} provider redirect missing after approval"
    return ""


def new_session() -> Any:
    if CurlCffiSession is not None:
        return CurlCffiSession(impersonate="chrome136")
    return requests.Session()


def explicit_proxy_for_link_type(proxy: str = "", link_type: str = "") -> str:
    explicit = normalize_proxy_url(proxy)
    if not explicit:
        return ""
    normalized_link_type = normalize_link_type(link_type)
    if normalized_link_type == "pix":
        return proxy_for_region(explicit, "BR")
    return explicit


def effective_default_proxy(proxy: str = "", link_type: str = "") -> str:
    explicit = explicit_proxy_for_link_type(proxy, link_type)
    if explicit:
        return explicit
    normalized_link_type = normalize_link_type(link_type)
    if normalized_link_type == "pix":
        return next_proxy("pix", PIX_PROXY_POOL or DEFAULT_PROXY_POOL, PIX_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "BR"))
    wallet_config = wallet_approval_line_config(normalized_link_type)
    if wallet_config:
        return next_proxy(
            normalized_link_type,
            GOPAY_PROVIDER_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, wallet_config["proxy_region"]),
            GOPAY_PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, wallet_config["proxy_region"]),
        )
    if normalized_link_type == "korea":
        return next_proxy(
            "korea",
            KOREA_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "KR"),
            KOREA_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "KR"),
        )
    if normalized_link_type == "swiss":
        return next_proxy(
            "swiss",
            SWISS_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "CH"),
            SWISS_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "CH"),
        )
    if normalized_link_type == "ideal":
        return next_proxy(
            "ideal",
            rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "NL"),
            proxy_for_region(DEFAULT_PROXY, "NL"),
        )
    if normalized_link_type == "upi":
        return next_proxy(
            "upi",
            INDIA_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "IN"),
            INDIA_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "IN"),
        )
    return next_proxy("default", DEFAULT_PROXY_POOL, DEFAULT_PROXY)


def proxy_candidates_for_link_type(proxy: str = "", link_type: str = "") -> list[str]:
    normalized_link_type = normalize_link_type(link_type)
    explicit = explicit_proxy_for_link_type(proxy, normalized_link_type)
    if explicit:
        return [explicit]
    if normalized_link_type == "pix":
        pool = PIX_PROXY_POOL or DEFAULT_PROXY_POOL
        fallback = PIX_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "BR")
    elif normalized_link_type == "korea":
        pool = KOREA_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "KR")
        fallback = KOREA_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "KR")
    elif normalized_link_type == "swiss":
        pool = SWISS_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "CH")
        fallback = SWISS_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "CH")
    elif normalized_link_type == "ideal":
        pool = rewrite_proxy_pool_region(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL, "NL")
        fallback = proxy_for_region(PROVIDER_STAGE_PROXY or DEFAULT_PROXY, "NL")
    elif normalized_link_type == "upi":
        pool = INDIA_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, "IN")
        fallback = INDIA_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "IN")
    elif wallet_approval_line_config(normalized_link_type):
        wallet_config = wallet_approval_line_config(normalized_link_type)
        pool = GOPAY_PROVIDER_PROXY_POOL or rewrite_proxy_pool_region(DEFAULT_PROXY_POOL, wallet_config["proxy_region"])
        fallback = GOPAY_PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, wallet_config["proxy_region"])
    else:
        pool = PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL
        fallback = PROVIDER_STAGE_PROXY or DEFAULT_PROXY

    candidates: list[str] = []
    seen = set()
    for item in list(pool) + [normalize_proxy_url(fallback)]:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        candidates.append(value)
    return candidates


def set_proxy_url(session: Any, proxy: str) -> None:
    proxy = normalize_proxy_url(proxy)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}


def set_proxy(session: Any, proxy: str, link_type: str = "") -> None:
    set_proxy_url(session, effective_default_proxy(proxy, link_type))


def normalize_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def effective_zc_base_url(explicit: str = "") -> str:
    return normalize_base_url(explicit or ZC_DEFAULT_BASE_URL)


def effective_zc_token(explicit: str = "") -> str:
    token = str(explicit or ZC_DEFAULT_TOKEN or "").strip()
    if token:
        return token
    secret = str(ZC_DEFAULT_JWT_SECRET or "").strip()
    if not secret:
        return ""
    return create_zc_service_token(secret)


def effective_zc_password(explicit: str = "") -> str:
    return str(explicit or ZC_DEFAULT_PASSWORD or "").strip()


def effective_zc_claim_status(explicit: str = "") -> str:
    return str(explicit or ZC_DEFAULT_CLAIM_STATUS or "").strip()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def create_zc_service_token(secret: str, expire_seconds: int = 86400 * 7) -> str:
    now = int(time.time())
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url_encode(
        json.dumps(
            {
                "sub": "admin",
                "exp": now + int(expire_seconds),
                "iat": now,
            },
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64url_encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def proxy_for_region(proxy: str, region: str) -> str:
    proxy = str(proxy or "").strip()
    region = str(region or "").strip().upper()
    if proxy and region and "region-" in proxy:
        return re.sub(r"region-[A-Za-z]{2}", f"region-{region}", proxy)
    return proxy


def provider_stage_proxy(req: LongLinkRequest) -> str:
    normalized_link_type = normalize_link_type(req.link_type)
    explicit = explicit_proxy_for_link_type(req.proxy, normalized_link_type)
    if explicit:
        return explicit
    if normalized_link_type == "korea":
        return next_proxy(
            "korea",
            KOREA_PROXY_POOL or rewrite_proxy_pool_region(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL, "KR"),
            KOREA_STAGE_PROXY or PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "KR"),
        )
    if normalized_link_type == "ideal":
        return next_proxy(
            "ideal",
            rewrite_proxy_pool_region(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL, "NL"),
            proxy_for_region(PROVIDER_STAGE_PROXY or DEFAULT_PROXY, "NL"),
        )
    if normalized_link_type == "pix":
        return next_proxy(
            "pix",
            PIX_PROXY_POOL or rewrite_proxy_pool_region(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL, "BR"),
            PIX_STAGE_PROXY or PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "BR"),
        )
    wallet_config = wallet_approval_line_config(req.link_type)
    if wallet_config:
        return next_proxy(
            normalize_link_type(req.link_type),
            GOPAY_PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL,
            GOPAY_PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, wallet_config["proxy_region"]),
        )
    if normalized_link_type == "upi":
        return next_proxy(
            "upi",
            INDIA_PROXY_POOL or rewrite_proxy_pool_region(PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL, "IN"),
            INDIA_STAGE_PROXY or PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "IN"),
        )
    return next_proxy(
        "provider",
        PROVIDER_PROXY_POOL or DEFAULT_PROXY_POOL,
        PROVIDER_STAGE_PROXY or proxy_for_region(DEFAULT_PROXY, "US"),
    )


def apply_provider_proxy(chatgpt: Any, proxy: str) -> None:
    set_proxy_url(chatgpt, proxy)


def currency_for_country(country: str) -> str:
    return COUNTRY_CURRENCY.get(str(country or "").upper(), "USD")


def normalize_country(country: str) -> str:
    country = str(country or "").strip().upper()
    return country if country in COUNTRY_CURRENCY else "US"


def normalize_link_type(link_type: str) -> str:
    value = str(link_type or "hosted").strip().lower()
    aliases = {
        "payment": "hosted",
        "pay": "hosted",
        "long": "hosted",
        "kr": "korea",
        "korea": "korea",
        "korean": "korea",
        "ch": "swiss",
        "swiss": "swiss",
        "twint": "swiss",
        "nl": "ideal",
        "netherlands": "ideal",
        "ideal": "ideal",
        "ideal_nl": "ideal",
        "ideal-nl": "ideal",
        "in": "upi",
        "india": "upi",
        "ind": "upi",
        "upi": "upi",
        "pp": "paypal",
        "paypal": "paypal",
        "gcash": "gcash",
        "gopy": "gopay",
        "gopay": "gopay",
        "grabpay": "grabpay",
        "pix": "pix",
    }
    return aliases.get(value, "hosted")


def payment_method_type_for_link_type(link_type: str) -> str:
    normalized = normalize_link_type(link_type)
    if normalized == "korea":
        return "kakao_pay"
    if normalized == "swiss":
        return "twint"
    if normalized == "ideal":
        return "ideal"
    if normalized == "upi":
        return "upi"
    if normalized in {"pix", "gopay", "gcash", "grabpay", "paypal"}:
        return normalized
    return "paypal"


def normalize_provider_payment_method_type(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "gopy": "gopay",
        "gopay": "gopay",
        "gcash": "gcash",
        "grabpay": "grabpay",
        "pix": "pix",
        "paypal": "paypal",
        "pay": "paypal",
        "hosted": "paypal",
        "kr": "kakao_pay",
        "korea": "kakao_pay",
        "korean": "kakao_pay",
        "kakao": "kakao_pay",
        "kakaopay": "kakao_pay",
        "kakao_pay": "kakao_pay",
        "ch": "twint",
        "swiss": "twint",
        "twint": "twint",
        "nl": "ideal",
        "netherlands": "ideal",
        "ideal": "ideal",
        "ideal_nl": "ideal",
        "ideal-nl": "ideal",
        "in": "upi",
        "india": "upi",
        "upi": "upi",
        "id": "gopay",
        "indonesia": "gopay",
        "ph": "gcash",
        "philippines": "gcash",
    }
    if raw in aliases:
        return aliases[raw]
    return payment_method_type_for_link_type(raw)


def effective_country(req: LongLinkRequest) -> str:
    link_type = normalize_link_type(req.link_type)
    if link_type == "paypal":
        return "US"
    wallet_config = wallet_approval_line_config(link_type)
    if wallet_config:
        return wallet_config["country"]
    if link_type == "pix":
        return "BR"
    if link_type == "korea":
        return "KR"
    if link_type == "swiss":
        return "CH"
    if link_type == "ideal":
        return "NL"
    if link_type == "upi":
        return "IN"
    return normalize_country(req.billing_country)


def locale_parts(locale: str) -> tuple[str, str]:
    return LOCALE_MAP.get(str(locale or "").strip(), LOCALE_MAP["en"])


def effective_payment_locale(link_type: str, requested: str = "") -> str:
    normalized = normalize_link_type(link_type)
    if normalized == "pix":
        return "pt-BR"
    if normalized == "korea":
        return "ko"
    if normalized == "swiss":
        return "de"
    if normalized == "ideal":
        return "nl"
    if normalized == "upi":
        return "en"
    wallet_config = wallet_approval_line_config(normalized)
    if wallet_config:
        return wallet_config["payment_locale"]
    value = str(requested or "en").strip()
    return value or "en"


def browser_timezone_for_link_type(link_type: str) -> str:
    normalized = normalize_link_type(link_type)
    if normalized == "pix":
        return "America/Sao_Paulo"
    wallet_config = wallet_approval_line_config(normalized)
    if wallet_config:
        return wallet_config["timezone"]
    if normalized == "korea":
        return "Asia/Seoul"
    if normalized == "swiss":
        return "Europe/Zurich"
    if normalized == "ideal":
        return "Europe/Amsterdam"
    if normalized == "upi":
        return "Asia/Kolkata"
    return "Asia/Shanghai"


def normalize_buyer_tax_id(raw: str) -> str:
    value = re.sub(r"\D+", "", str(raw or ""))
    if len(value) in (11, 14):
        return value
    return str(raw or "").strip()


def generate_random_cpf() -> str:
    while True:
        digits = [random.randint(0, 9) for _ in range(9)]
        if len(set(digits)) > 1:
            break

    def check_digit(base: list[int], start_weight: int) -> int:
        total = sum(digit * (start_weight - idx) for idx, digit in enumerate(base))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    first = check_digit(digits, 10)
    second = check_digit(digits + [first], 11)
    return "".join(str(digit) for digit in digits + [first, second])


def find_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("accessToken", "access_token", "token"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        for item in value.values():
            token = find_token(item)
            if token:
                return token
    if isinstance(value, list):
        for item in value:
            token = find_token(item)
            if token:
                return token
    return ""


def normalize_access_token(raw: str) -> str:
    token = str(raw or "").strip()
    if not token:
        return ""
    if token.startswith("{") or token.startswith("["):
        try:
            return find_token(json.loads(token)) or token
        except json.JSONDecodeError:
            return token
    return token


def parse_bearer_authorization(request: Request) -> str:
    header = str(request.headers.get("Authorization") or "").strip()
    if not header.lower().startswith("bearer "):
        return ""
    return header[7:].strip()


def require_upi_service_token(request: Request) -> None:
    configured = [token for token in (UPI_SERVICE_TOKEN, UPI_BUSINESS_TOKEN) if token]
    if not configured:
        return
    bearer = parse_bearer_authorization(request)
    if any(hmac.compare_digest(bearer, token) for token in configured):
        return
    raise HTTPException(status_code=401, detail="upi authorization required")


def looks_like_jwt(token: str) -> bool:
    text = str(token or "").strip()
    if not text.startswith("eyJ"):
        return False
    parts = text.split(".")
    return len(parts) == 3 and all(part.strip() for part in parts)


def decode_jwt_payload(raw_token: str) -> dict[str, Any]:
    token = normalize_access_token(raw_token)
    if not token or not looks_like_jwt(token):
        return {}
    try:
        payload_part = token.split(".", 2)[1]
        padded = payload_part + "=" * ((4 - len(payload_part) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def token_is_jwt_expired(raw_token: str) -> bool:
    payload = decode_jwt_payload(raw_token)
    exp = int(payload.get("exp") or 0)
    return bool(exp and exp <= int(time.time()))


def classify_registration_type(raw_token: str) -> tuple[str, str]:
    payload = decode_jwt_payload(raw_token)
    phone_number = str(
        payload.get("phone_number")
        or payload.get("phone")
        or payload.get("phoneNumber")
        or ""
    ).strip()
    if phone_number:
        return "phone", phone_number
    email = str(payload.get("email") or "").strip()
    if email:
        return "email", ""
    return "unknown", ""


def upi_reason_response(reason: str, *, retryable: bool, message: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "reason": reason,
            "retryable": retryable,
            "message": message,
        },
    )


def upi_error_response_from_exception(exc: Exception) -> JSONResponse:
    detail = progress_error_text(exc)
    lowered = detail.lower()
    if isinstance(exc, HTTPException) and exc.status_code == 401:
        return upi_reason_response("unauthorized", retryable=False, message=detail, status_code=401)
    if "upi authorization required" in lowered:
        return upi_reason_response("unauthorized", retryable=False, message=detail, status_code=401)
    if "operation timed out" in lowered or "timed out" in lowered:
        return upi_reason_response("server-error", retryable=True, message=detail)
    if "approve blocked" in lowered or "chatgpt approve unexpected result: 'blocked'" in lowered:
        return upi_reason_response("approve-blocked", retryable=False, message=detail)
    if "chatgpt approve failed" in lowered:
        return upi_reason_response("approve-blocked", retryable=False, message=detail)
    if "token_invalidated" in lowered or "authentication token has been invalidated" in lowered:
        return upi_reason_response("token-invalidated", retryable=False, message=detail)
    if "already-paid" in lowered or "already paid" in lowered:
        return upi_reason_response("already-paid", retryable=False, message=detail)
    if "checkout response missing short link" in lowered or "checkout failed" in lowered:
        return upi_reason_response("checkout-failed", retryable=True, message=detail)
    if "stripe confirm failed" in lowered:
        return upi_reason_response("confirm-failed", retryable=True, message=detail)
    if "upi payment failed" in lowered:
        return upi_reason_response("confirm-failed", retryable=False, message=detail)
    if "upi qr resolution timeout" in lowered:
        return upi_reason_response("no-next-action", retryable=False, message=detail)
    if "setup_intent id missing" in lowered:
        return upi_reason_response("no-next-action", retryable=False, message=detail)
    if "payment page qr fetch failed" in lowered:
        return upi_reason_response("server-error", retryable=True, message=detail)
    return upi_reason_response("server-error", retryable=True, message=detail, status_code=500 if not isinstance(exc, HTTPException) else 200)


def accept_language_for_browser_locale(locale: str) -> str:
    normalized = str(locale or "").strip() or "en-US"
    short = normalized.split("-", 1)[0]
    if short == normalized:
        return f"{normalized},{short};q=0.9,en-US;q=0.8,en;q=0.7"
    return f"{normalized},{short};q=0.9,en-US;q=0.8,en;q=0.7"


def extract_processor_entity(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    direct = data.get("processor_entity") or data.get("processorEntity")
    if direct:
        return str(direct).strip()
    for key in ("checkout_session", "session", "checkout", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = extract_processor_entity(nested)
            if found:
                return found
    return ""


def extract_checkout_url(
    data: Any,
    cs_id: str = "",
    processor_entity: str = "",
    country: str = "US",
) -> str:
    if isinstance(data, dict):
        for key in (
            "stripe_hosted_url",
            "checkout_url",
            "url",
            "openai_checkout_url",
            "return_url",
            "success_url",
            "hosted_url",
        ):
            value = str(data.get(key) or "").strip()
            if value:
                return value
        for nested in data.values():
            value = extract_checkout_url(nested, cs_id=cs_id, processor_entity=processor_entity, country=country)
            if value:
                return value
    elif isinstance(data, list):
        for nested in data:
            value = extract_checkout_url(nested, cs_id=cs_id, processor_entity=processor_entity, country=country)
            if value:
                return value

    text = ""
    try:
        text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = str(data or "")

    for pattern in (
        r"https://checkout\.stripe\.com[^\s\"']+",
        r"https://pay\.openai\.com[^\s\"']+",
        r"https://chatgpt\.com/checkout/[^\s\"']+",
        r"https://chatgpt\.com/checkout/verify[^\s\"']+",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(0)

    if cs_id:
        entity = processor_entity_for_country(country, processor_entity)
        return f"https://chatgpt.com/checkout/{entity}/{cs_id}"
    return ""


def build_chatgpt_session(req: LongLinkRequest) -> Any:
    access_token = normalize_access_token(req.access_token)
    if not access_token:
        raise HTTPException(status_code=400, detail="accessToken is required")

    device_id = req.device_id.strip() or str(uuid.uuid4())
    user_agent = req.user_agent.strip() or DEFAULT_USER_AGENT
    browser_locale, _ = locale_parts(effective_payment_locale(req.link_type, req.payment_locale))
    accept_language = accept_language_for_browser_locale(browser_locale)
    session = new_session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": accept_language,
            "Authorization": f"Bearer {access_token}",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "Content-Type": "application/json",
            "oai-device-id": device_id,
            "oai-language": browser_locale,
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "Cookie": f"oai-did={device_id}",
        }
    )
    set_proxy(session, req.proxy, req.link_type)
    return session


def zc_extract_access_token(account: dict[str, Any]) -> tuple[str, str]:
    for key in ("access_token", "accessToken", "token"):
        value = str(account.get(key) or "").strip()
        if value:
            return value, key

    extra = account.get("extra_json")
    extra_data: dict[str, Any] = {}
    if isinstance(extra, str) and extra.strip():
        try:
            extra_data = json.loads(extra)
        except json.JSONDecodeError:
            extra_data = {}
    elif isinstance(extra, dict):
        extra_data = extra

    for key in ("access_token", "accessToken"):
        value = str(extra_data.get(key) or "").strip()
        if value:
            return value, key

    direct_token = str(account.get("token") or "").strip()
    if direct_token:
        return direct_token, "token"

    return "", ""


def zc_normalize_account(account: dict[str, Any]) -> dict[str, Any]:
    access_token, token_source = zc_extract_access_token(account)
    extra = account.get("extra_json")
    extra_data: dict[str, Any] = {}
    if isinstance(extra, str) and extra.strip():
        try:
            extra_data = json.loads(extra)
        except json.JSONDecodeError:
            extra_data = {}
    elif isinstance(extra, dict):
        extra_data = extra

    return {
        "id": account.get("id"),
        "email": str(account.get("email") or "").strip(),
        "password": str(account.get("password") or "").strip(),
        "access_token": access_token,
        "refresh_token": str(
            account.get("refresh_token")
            or account.get("refreshToken")
            or ""
        ).strip() or str(
            extra_data.get("refresh_token")
            or extra_data.get("refreshToken")
            or ""
        ).strip(),
        "status": str(account.get("status") or "").strip(),
        "created_at": str(account.get("created_at") or "").strip(),
        "updated_at": str(account.get("updated_at") or "").strip(),
        "token_source": token_source,
    }


def zc_login(base_url: str, password: str) -> str:
    session = new_session()
    response = session.post(
        urljoin(f"{base_url}/", "api/auth/login"),
        json={"password": password},
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC 登录失败: {response.text[:300]}",
        )
    data = response.json() or {}
    token = str(data.get("access_token") or "").strip()
    if not token:
        if data.get("requires_2fa"):
            raise HTTPException(status_code=400, detail="ZC 已开启 2FA，当前接入不支持")
        raise HTTPException(status_code=502, detail="ZC 登录响应里没有 access_token")
    return token


def zc_resolve_token(base_url: str, token: str = "", password: str = "") -> str:
    bearer = str(token or "").strip()
    if bearer:
        return bearer
    password_value = str(password or "").strip()
    if not password_value:
        raise HTTPException(status_code=400, detail="token or password is required")
    return zc_login(base_url, password_value)


def zc_fetch_accounts(req: ZCAccountsRequest) -> list[dict[str, Any]]:
    base_url = effective_zc_base_url(req.base_url)
    if not base_url:
        raise HTTPException(status_code=400, detail="baseUrl is required")

    bearer = zc_resolve_token(base_url, effective_zc_token(req.token), effective_zc_password(req.password))

    page_size = max(1, min(int(req.page_size or 100), 500))
    session = new_session()
    session.headers.update({"Authorization": f"Bearer {bearer}"})

    params: dict[str, Any] = {
        "platform": "chatgpt",
        "page": 1,
        "page_size": page_size,
    }
    if req.status:
        params["status"] = req.status
    if req.has_rt is not None:
        params["has_rt"] = "true" if req.has_rt else "false"

    response = session.get(
        urljoin(f"{base_url}/", "api/accounts"),
        params=params,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC 拉取账号失败: {response.text[:300]}",
        )
    data = response.json() or {}
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="ZC 账号接口返回格式异常")
    return [zc_normalize_account(item) for item in items if isinstance(item, dict)]


def zc_pick_account(req: ZCClaimRequest) -> dict[str, Any]:
    accounts = zc_fetch_accounts(
        ZCAccountsRequest(
            baseUrl=effective_zc_base_url(req.base_url),
            token=effective_zc_token(req.token),
            password=effective_zc_password(req.password),
            pageSize=ZC_PICK_PAGE_SIZE,
            status=str(req.status or "").strip(),
            hasRt=None,
        )
    )
    usable = [account for account in accounts if str(account.get("access_token") or "").strip()]
    if not usable:
        raise HTTPException(status_code=409, detail="ZC 列表里没有带 access_token 的可用账号")
    picked = random.choice(usable)
    return {
        **picked,
        "claim_key": "",
        "claim_expires_at": "",
    }


def zc_claim_account(req: ZCClaimRequest) -> dict[str, Any]:
    base_url = effective_zc_base_url(req.base_url)
    if not base_url:
        raise HTTPException(status_code=400, detail="baseUrl is required")
    claim_key = str(req.claim_key or "").strip()
    if not claim_key:
        raise HTTPException(status_code=400, detail="claimKey is required")

    bearer = zc_resolve_token(base_url, effective_zc_token(req.token), effective_zc_password(req.password))
    session = new_session()
    session.headers.update({"Authorization": f"Bearer {bearer}"})
    payload: dict[str, Any] = {
        "platform": "chatgpt",
        "claim_key": claim_key,
        "source": "opll",
        "selection_mode": "random",
        "auth_requirement": "session_or_access",
        "require_session_or_token": True,
        "lease_seconds": max(30, int(req.lease_seconds or 1800)),
    }
    if req.status:
        payload["status"] = str(req.status or "").strip()

    response = session.post(
        urljoin(f"{base_url}/", "api/accounts/claim"),
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC claim 失败: {response.text[:300]}",
        )
    data = response.json() or {}
    account = data.get("account")
    if not isinstance(account, dict):
        raise HTTPException(status_code=502, detail="ZC claim 返回格式异常")
    normalized = zc_normalize_account(account)
    normalized["claim_key"] = str(account.get("claim_key") or claim_key).strip()
    normalized["claim_expires_at"] = str(account.get("claim_expires_at") or "").strip()
    return normalized


def zc_release_account(req: ZCReleaseRequest) -> dict[str, Any]:
    base_url = effective_zc_base_url(req.base_url)
    if not base_url:
        raise HTTPException(status_code=400, detail="baseUrl is required")
    claim_key = str(req.claim_key or "").strip()
    if not claim_key:
        raise HTTPException(status_code=400, detail="claimKey is required")

    bearer = zc_resolve_token(base_url, effective_zc_token(req.token), effective_zc_password(req.password))
    session = new_session()
    session.headers.update({"Authorization": f"Bearer {bearer}"})
    payload: dict[str, Any] = {"claim_key": claim_key}
    if req.account_id:
        payload["account_id"] = int(req.account_id)

    response = session.post(
        urljoin(f"{base_url}/", "api/accounts/release"),
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC release 失败: {response.text[:300]}",
        )
    return response.json() or {"ok": True}


def zc_delete_account(
    *,
    base_url: str,
    token: str = "",
    password: str = "",
    account_id: int = 0,
) -> dict[str, Any]:
    normalized_base_url = normalize_base_url(base_url)
    if not normalized_base_url:
        raise HTTPException(status_code=400, detail="baseUrl is required")
    if int(account_id or 0) <= 0:
        raise HTTPException(status_code=400, detail="account_id is required")
    bearer = zc_resolve_token(
        normalized_base_url,
        effective_zc_token(token),
        effective_zc_password(password),
    )
    session = new_session()
    session.headers.update({"Authorization": f"Bearer {bearer}"})
    response = session.delete(
        urljoin(f"{normalized_base_url}/", f"api/accounts/{int(account_id)}"),
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC delete 失败: {response.text[:300]}",
        )
    return response.json() or {"ok": True}


def zc_mark_payment_succeeded(
    *,
    base_url: str,
    token: str = "",
    password: str = "",
    account_id: int = 0,
    email: str = "",
    claim_key: str = "",
    payment_session_id: str = "",
    payment_channel: str = "pix",
) -> dict[str, Any]:
    normalized_base_url = normalize_base_url(base_url)
    if not normalized_base_url:
        raise HTTPException(status_code=400, detail="baseUrl is required")
    bearer = zc_resolve_token(
        normalized_base_url,
        effective_zc_token(token),
        effective_zc_password(password),
    )
    session = new_session()
    session.headers.update({"Authorization": f"Bearer {bearer}"})
    payload: dict[str, Any] = {
        "email": str(email or "").strip(),
        "payment_session_id": str(payment_session_id or "").strip(),
        "payment_channel": str(payment_channel or "pix").strip() or "pix",
        "payment_status": "succeeded",
        "claim_key": str(claim_key or "").strip(),
    }
    if account_id > 0:
        payload["account_id"] = int(account_id)
    response = session.post(
        urljoin(f"{normalized_base_url}/", "api/chatgpt/payment-succeeded"),
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"ZC payment-succeeded 失败: {response.text[:300]}",
        )
    return response.json() or {"ok": True}


def maybe_claim_zc_account(req: LongLinkRequest, job_id: str) -> dict[str, Any] | None:
    if not req.auto_claim_zc:
        return None
    set_progress(job_id, percent=4, text="从 ZC 列表取账号", done=False, error=False)
    claim_key = str(req.zc_claim_key or "").strip() or progress_job_id(req.job_id)
    claimed = zc_pick_account(
        ZCClaimRequest(
            baseUrl=effective_zc_base_url(req.zc_base_url),
            token=effective_zc_token(req.zc_token),
            password=effective_zc_password(req.zc_password),
            claimKey=claim_key,
            status=effective_zc_claim_status(req.zc_claim_status),
            leaseSeconds=max(int(req.zc_claim_lease_seconds or 0), 6 * 60 * 60),
        )
    )
    if not claimed.get("access_token"):
        raise HTTPException(status_code=409, detail="ZC 取到的账号没有 access_token")
    req.access_token = str(claimed.get("access_token") or "").strip()
    return claimed


def zc_account_has_claim(account: dict[str, Any]) -> bool:
    return int(account.get("id") or 0) > 0


def detect_fatal_account_error(exc: Exception) -> str:
    detail_text = progress_error_text(exc).lower()
    if isinstance(exc, HTTPException) and int(exc.status_code or 0) == 401:
        return "http_401"
    if '"status": 401' in detail_text or " status 401" in detail_text or "http 401" in detail_text:
        return "http_401"
    if "token_invalidated" in detail_text or "authentication token has been invalidated" in detail_text:
        return "token_invalidated"
    if "account_deactivated" in detail_text or "deleted or deactivated" in detail_text:
        return "account_deactivated"
    if "access_token_invalid" in detail_text:
        return "access_token_invalid"
    if "session_invalid" in detail_text:
        return "session_invalid"
    return ""


def should_include_initial_checkout_promo(req: LongLinkRequest, link_type: str) -> bool:
    if not req.use_promo_params:
        return False
    if link_type in {"korea", "pix"}:
        return False
    return True


def checkout_request_body(req: LongLinkRequest) -> dict[str, Any]:
    billing_country = effective_country(req)
    currency = currency_for_country(billing_country)
    checkout_ui_mode = (req.checkout_ui_mode or "custom").strip() or "custom"
    link_type = normalize_link_type(req.link_type)
    body = {
        "entry_point": "all_plans_pricing_modal",
        "plan_name": "chatgptplusplan",
        "billing_details": {
            "country": billing_country,
            "currency": currency,
        },
        "checkout_ui_mode": checkout_ui_mode,
    }
    promo_id = str(getattr(req, "promo_id", "") or "plus-1-month-free").strip() or "plus-1-month-free"
    if should_include_initial_checkout_promo(req, link_type):
        body["promo_campaign"] = {
            "promo_campaign_id": promo_id,
            "is_coupon_from_query_param": False,
        }
    return body


def checkout_request_headers() -> dict[str, str]:
    return {
        "Referer": "https://chatgpt.com/",
        "x-openai-target-path": "/backend-api/payments/checkout",
        "x-openai-target-route": "/backend-api/payments/checkout",
    }


def checkout_challenge_detected(response: Any, body_text: str) -> bool:
    content_type = str(response.headers.get("Content-Type") or "").lower()
    cf_mitigated = str(response.headers.get("cf-mitigated") or "").strip().lower()
    normalized = str(body_text or "").lower()
    if cf_mitigated == "challenge":
        return True
    if "text/html" not in content_type and not normalized.startswith("<html"):
        return False
    return any(marker in normalized for marker in CHECKOUT_CHALLENGE_MARKERS)


def checkout_payment_method_tokens(data: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    groups = (
        data.get("payment_method_types"),
        data.get("custom_payment_methods"),
    )
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            candidates: list[str] = []
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                for key in ("type", "id", "name", "payment_method_type"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)
            for raw in candidates:
                normalized = normalize_provider_payment_method_type(raw)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                tokens.append(normalized)
    return tokens


def ensure_checkout_supports_requested_wallet(data: dict[str, Any], req: LongLinkRequest) -> None:
    requested = normalize_link_type(req.link_type)
    if requested not in {"gcash", "grabpay"}:
        return
    available = checkout_payment_method_tokens(data)
    if requested in available:
        return
    available_text = ", ".join(available) if available else "none"
    raise HTTPException(
        status_code=409,
        detail=(
            f"{requested} line is unavailable for this checkout. "
            f"OpenAI returned payment methods: {available_text}"
        ),
    )


def parse_checkout_response(response: Any, req: LongLinkRequest) -> dict[str, Any]:
    body_text = response.text[:500] if response.text else ""
    if response.status_code >= 400:
        if checkout_challenge_detected(response, body_text):
            raise HTTPException(status_code=503, detail=f"checkout challenge blocked: {body_text}")
        if "cannot combine currencies" in body_text.lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    "GoPay needs an IDR checkout, but this Stripe customer already has active USD "
                    "checkout/subscription state. Use a fresh account/customer or wait for the USD "
                    "checkout state to expire; this cannot be bypassed in code."
                ),
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"checkout create failed: {body_text}",
        )

    data = response.json() or {}
    ensure_checkout_supports_requested_wallet(data, req)
    cs_id = data.get("checkout_session_id") or data.get("session_id") or data.get("id")
    if not cs_id or not str(cs_id).startswith(("cs_", "oaics_")):
        raise HTTPException(status_code=502, detail=f"checkout response missing cs_id: {data}")
    billing_country = effective_country(req)
    processor_entity = extract_processor_entity(data)
    return {
        "cs_id": str(cs_id),
        "processor_entity": processor_entity,
        "billing_country": billing_country,
        "currency": currency_for_country(billing_country),
        "publishable_key": str(data.get("publishable_key") or data.get("publishableKey") or "").strip(),
        "checkout_url": extract_checkout_url(
            data,
            cs_id=str(cs_id),
            processor_entity=processor_entity,
            country=billing_country,
        ),
    }


def is_checkout_challenge_exception(exc: Exception) -> bool:
    return "checkout challenge blocked:" in progress_error_text(exc).lower()


def is_checkout_retryable_exception(exc: Exception) -> bool:
    if is_checkout_challenge_exception(exc) or isinstance(exc, requests.RequestException):
        return True
    return CurlCffiRequestsError is not None and isinstance(exc, CurlCffiRequestsError)


def create_checkout(req: LongLinkRequest, chatgpt_session: Any | None = None) -> dict[str, Any]:
    response = (chatgpt_session or build_chatgpt_session(req)).post(
        "https://chatgpt.com/backend-api/payments/checkout",
        json=checkout_request_body(req),
        headers=checkout_request_headers(),
        timeout=DEFAULT_TIMEOUT,
    )
    return parse_checkout_response(response, req)


def create_checkout_with_proxy_retry(req: LongLinkRequest) -> tuple[dict[str, Any], Any]:
    proxy_candidates = proxy_candidates_for_link_type(req.proxy, req.link_type)
    attempt_count = min(max(1, len(proxy_candidates)), MAX_CHECKOUT_PROXY_ATTEMPTS)
    last_error: Exception | None = None
    for attempt_index, proxy_value in enumerate(proxy_candidates[:attempt_count], start=1):
        chatgpt = build_chatgpt_session(req)
        set_proxy_url(chatgpt, proxy_value)
        try:
            checkout = create_checkout(req, chatgpt)
            if attempt_index > 1:
                log_event(
                    "checkout.retry_succeeded",
                    "checkout succeeded after proxy retry",
                    status=f"attempt={attempt_index}",
                )
            return checkout, chatgpt
        except Exception as exc:
            last_error = exc
            if not is_checkout_retryable_exception(exc):
                raise
            log_event(
                "checkout.retry",
                "checkout challenge detected, retrying with next proxy",
                status=f"attempt={attempt_index}",
            )
    if last_error is not None:
        raise last_error
    raise HTTPException(status_code=502, detail="checkout create failed: no proxy candidates available")


def checkout_update_headers(path: str, checkout: dict[str, Any]) -> dict[str, str]:
    referer = f"https://chatgpt.com/checkout/{checkout['processor_entity']}/{checkout['cs_id']}"
    return {"Referer": referer, "x-openai-target-path": path, "x-openai-target-route": path}


def pix_checkout_email(claimed_account: dict[str, Any] | None) -> str:
    if isinstance(claimed_account, dict):
        email = str(claimed_account.get("email") or "").strip()
        if email:
            return email
    return PIX_BILLING_EMAIL


def pix_promotion_proxy(provider_proxy: str) -> str:
    configured = next_proxy(
        "pix_promotion",
        PIX_PROMOTION_PROXY_POOL,
        PIX_PROMOTION_STAGE_PROXY,
    )
    if configured:
        return configured
    seed = normalize_proxy_url(provider_proxy) or proxy_for_region(DEFAULT_PROXY, "BR")
    return proxy_for_region(seed, PIX_PROMOTION_REGION)


def update_pix_checkout_promotion(chatgpt: Any, checkout: dict[str, Any], proxy: str) -> None:
    set_proxy_url(chatgpt, proxy)
    path = "/backend-api/payments/checkout/update"
    body = {
        "checkout_session_id": checkout["cs_id"],
        "processor_entity": checkout["processor_entity"],
        "plan_name": "chatgptplusplan",
        "price_interval": "month",
        "seat_quantity": 1,
        "promo_campaign": {"promo_campaign_id": PIX_PROMO_ID, "is_coupon_from_query_param": False},
    }
    response = chatgpt.post("https://chatgpt.com" + path, json=body, headers=checkout_update_headers(path, checkout), timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=f"pix checkout update failed: {response.text[:500]}")
    payload = response.json() or {}
    if payload.get("success") is False:
        raise HTTPException(status_code=409, detail=f"pix checkout promotion rejected: {payload}")


def update_pix_checkout_taxes_br(chatgpt: Any, checkout: dict[str, Any], email: str, proxy: str) -> None:
    set_proxy_url(chatgpt, proxy)
    path = "/backend-api/payments/checkout/taxes"
    body = pix_br_taxes_body(checkout, email)
    response = chatgpt.post("https://chatgpt.com" + path, json=body, headers=checkout_update_headers(path, checkout), timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=f"pix checkout taxes failed: {response.text[:500]}")
    response.json()


def pix_br_taxes_body(checkout: dict[str, Any], email: str) -> dict[str, Any]:
    return {
        "checkout_session_id": checkout["cs_id"],
        "checkout_email": str(email or PIX_BILLING_EMAIL).strip() or PIX_BILLING_EMAIL,
        "billing_country": PIX_BILLING_COUNTRY,
        "billing_name": PIX_BILLING_NAME,
        "currency": PIX_BILLING_CURRENCY,
        "tax_id": None,
        "processor_entity": checkout["processor_entity"],
        "billing_address": {
            "line1": PIX_BILLING_LINE1,
            "city": PIX_BILLING_CITY,
            "country": PIX_BILLING_COUNTRY,
            "postal_code": PIX_BILLING_POSTAL_CODE,
        },
    }


def stripe_update_pix_tax_region_br(req: LongLinkRequest, cs_id: str, stripe_pk: str, proxy: str) -> None:
    stripe = build_stripe_session(req, proxy_override=proxy)
    body = {
        "eid": "NA",
        "tax_region[country]": PIX_BILLING_COUNTRY,
        "tax_region[postal_code]": PIX_BILLING_POSTAL_CODE,
        "tax_region[line1]": PIX_BILLING_LINE1,
        "tax_region[city]": PIX_BILLING_CITY,
        "key": stripe_pk,
    }
    response = stripe.post(f"https://api.stripe.com/v1/payment_pages/{cs_id}", data=body, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=f"pix stripe tax_region failed: {response.text[:500]}")
    response.json()


def sync_pix_promotion_and_br_taxes(
    chatgpt: Any,
    checkout: dict[str, Any],
    req: LongLinkRequest,
    provider_proxy: str,
    claimed_account: dict[str, Any] | None,
    job_id: str,
) -> None:
    vn_proxy = pix_promotion_proxy(provider_proxy)
    log_event("pix.proxy_chain", "BR checkout/init -> VN checkout/update promotion -> VN tax calls with BR country -> BR final Stripe init", job_id=job_id, status="active")
    update_pix_checkout_promotion(chatgpt, checkout, vn_proxy)
    log_event("pix.promotion", f"VN checkout/update ok promo={PIX_PROMO_ID}", job_id=job_id, status="ok", cs_id=checkout["cs_id"])
    email = pix_checkout_email(claimed_account)
    update_pix_checkout_taxes_br(chatgpt, checkout, email, vn_proxy)
    log_event("pix.chatgpt_taxes", "BR ChatGPT taxes country=BR", job_id=job_id, status="ok", cs_id=checkout["cs_id"])
    stripe_pk = req.stripe_publishable_key.strip() or str(checkout.get("publishable_key") or "").strip() or DEFAULT_STRIPE_PK
    stripe_update_pix_tax_region_br(req, checkout["cs_id"], stripe_pk, vn_proxy)
    log_event("pix.tax_region", "BR Stripe tax_region country=BR", job_id=job_id, status="ok", cs_id=checkout["cs_id"])


def stripe_init(cs_id: str, req: LongLinkRequest, proxy_override: str = "") -> dict[str, Any]:
    stripe_pk = req.stripe_publishable_key.strip() or DEFAULT_STRIPE_PK
    browser_locale, elements_locale = locale_parts(effective_payment_locale(req.link_type, req.payment_locale))
    stripe = new_session()
    stripe.headers.update(
        {
            "User-Agent": req.user_agent.strip() or DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    if proxy_override:
        set_proxy_url(stripe, proxy_override)
    else:
        set_proxy(stripe, req.proxy, req.link_type)
    body = {
        "browser_locale": browser_locale,
        "browser_timezone": browser_timezone_for_link_type(req.link_type),
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[stripe_js_id]": str(uuid.uuid4()),
        "elements_session_client[locale]": elements_locale,
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
    }
    response = stripe.post(
        f"https://api.stripe.com/v1/payment_pages/{cs_id}/init",
        data=body,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"stripe init failed: {response.text[:500]}",
        )
    return response.json() or {}


def stripe_init_gopay_checksum(stripe: Any, cs_id: str, stripe_pk: str, req: LongLinkRequest) -> str:
    browser_locale, elements_locale = locale_parts(effective_payment_locale(req.link_type, req.payment_locale))
    body = {
        "browser_locale": browser_locale,
        "browser_timezone": browser_timezone_for_link_type(req.link_type),
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[stripe_js_id]": str(uuid.uuid4()),
        "elements_session_client[locale]": elements_locale,
        "elements_session_client[is_aggregation_expected]": "false",
        "key": stripe_pk,
    }
    response = stripe.post(
        f"https://api.stripe.com/v1/payment_pages/{cs_id}/init",
        data=body,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=f"stripe gopay init failed: {response.text[:500]}")
    checksum = str((response.json() or {}).get("init_checksum") or "").strip()
    if not checksum:
        raise HTTPException(status_code=502, detail=f"stripe gopay init missing init_checksum: {response.text[:300]}")
    return checksum


def to_openai_pay_url(stripe_hosted_url: str) -> str:
    url = str(stripe_hosted_url or "").strip()
    if not url:
        return ""
    if url.startswith("https://checkout.stripe.com"):
        return "https://pay.openai.com" + url[len("https://checkout.stripe.com") :]

    parsed = urlsplit(url)
    if parsed.netloc.lower() == "checkout.stripe.com":
        return urlunsplit((parsed.scheme or "https", "pay.openai.com", parsed.path, parsed.query, parsed.fragment))
    return url


def processor_entity_for_country(country: str, processor_entity: str = "") -> str:
    entity = str(processor_entity or "").strip()
    if entity:
        return entity
    return "openai_llc" if str(country or "").upper() == "US" else "openai_ie"


def chatgpt_success_return_url(cs_id: str, country: str, processor_entity: str = "") -> str:
    entity = processor_entity_for_country(country, processor_entity)
    return f"https://chatgpt.com/checkout/verify?stripe_session_id={cs_id}&processor_entity={entity}&plan_type=plus"


def stripe_checkout_long_url(cs_id: str, country: str, processor_entity: str = "") -> str:
    return (
        f"https://checkout.stripe.com/c/pay/{cs_id}"
        f"?returned_from_redirect=true&ui_mode=custom&return_url="
        f"{quote(chatgpt_success_return_url(cs_id, country, processor_entity), safe='')}"
    )


def stripe_confirm_return_url(cs_id: str, checkout: dict[str, Any], stripe_hosted_url: str) -> str:
    hosted_url = to_openai_pay_url(stripe_hosted_url) or stripe_checkout_long_url(
        cs_id,
        checkout["billing_country"],
        checkout.get("processor_entity", ""),
    )
    if "pay.openai.com/" in hosted_url or "checkout.stripe.com/" in hosted_url:
        parsed = urlsplit(hosted_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault(
            "success_return_url",
            chatgpt_success_return_url(
                cs_id,
                checkout["billing_country"],
                checkout.get("processor_entity", ""),
            ),
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return hosted_url


def expected_amount(init_payload: Any) -> str:
    if not isinstance(init_payload, dict):
        return "0"
    total_summary = init_payload.get("total_summary")
    if isinstance(total_summary, dict) and total_summary.get("due") is not None:
        return str(total_summary.get("due"))
    invoice = init_payload.get("invoice")
    if isinstance(invoice, dict) and invoice.get("amount_due") is not None:
        return str(invoice.get("amount_due"))
    line_items = init_payload.get("line_items")
    if isinstance(line_items, list):
        total = 0
        found = False
        for item in line_items:
            if isinstance(item, dict) and item.get("amount") is not None:
                try:
                    total += int(item.get("amount") or 0)
                    found = True
                except Exception:
                    pass
        if found:
            return str(total)
    return "0"


def expected_amount_int(init_payload: Any) -> int:
    try:
        return int(expected_amount(init_payload) or 0)
    except (TypeError, ValueError):
        return 0


def ensure_pix_is_offered(init_payload: dict[str, Any], stage: str) -> list[str]:
    methods = checkout_payment_method_tokens(init_payload)
    if methods and "pix" not in methods:
        available_text = ",".join(methods) if methods else "none"
        raise HTTPException(
            status_code=409,
            detail=f"pix line is unavailable for this {stage}. Returned payment methods: {available_text}",
        )
    return methods


def pix_final_init_checked(
    checkout: dict[str, Any],
    req: LongLinkRequest,
    provider_proxy: str,
    job_id: str,
) -> dict[str, Any]:
    init_payload = stripe_init(checkout["cs_id"], req, proxy_override=provider_proxy)
    amount = expected_amount_int(init_payload)
    methods = ensure_pix_is_offered(init_payload, "final stripe init")
    methods_text = ",".join(methods) or "none"
    log_event("pix.final_init", f"BR final Stripe init amount={amount} methods={methods_text}", job_id=job_id, status="ok", cs_id=checkout["cs_id"])
    if amount > PIX_MAX_AMOUNT_CENTS:
        raise HTTPException(status_code=409, detail=f"pix amount policy failed after BR tax sync: amount={amount}, allowed<={PIX_MAX_AMOUNT_CENTS}")
    return init_payload


def stripe_context(cs_id: str, init_payload: dict[str, Any], req: LongLinkRequest) -> dict[str, Any]:
    _, elements_locale = locale_parts(effective_payment_locale(req.link_type, req.payment_locale))
    return {
        "stripe_js_id": str(uuid.uuid4()),
        "elements_session_id": f"elements_session_{uuid.uuid4().hex[:11]}",
        "elements_session_config_id": str(init_payload.get("config_id") or uuid.uuid4()),
        "config_id": init_payload.get("config_id") or "",
        "init_checksum": init_payload.get("init_checksum") or "",
        "currency": str(init_payload.get("currency") or currency_for_country(effective_country(req))).lower(),
        "checkout_amount": expected_amount(init_payload),
        "locale": elements_locale,
    }


def billing_for_link_type(link_type: str, buyer_tax_id: str = "") -> dict[str, str]:
    normalized = normalize_link_type(link_type)
    if normalized == "paypal":
        first_name, last_name = random.choice(JAPAN_BILLING_NAMES)
        line1, city, state, postal_code = random.choice(JAPAN_BILLING_STREETS)
        suffix = random.randint(1000, 9999)
        return {
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
            "country": "JP",
            "line1": line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
    if normalized in {"gcash", "grabpay"}:
        first_name, last_name = random.choice(PHILIPPINES_BILLING_NAMES)
        line1, city, state, postal_code = random.choice(PHILIPPINES_BILLING_STREETS)
        suffix = random.randint(1000, 9999)
        return {
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
            "country": "PH",
            "line1": line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
    if normalized == "gopay":
        first_name, last_name = random.choice(INDONESIA_BILLING_NAMES)
        line1, city, state, postal_code = random.choice(INDONESIA_BILLING_STREETS)
        suffix = random.randint(1000, 9999)
        return {
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
            "country": "ID",
            "line1": line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
    if normalized == "pix":
        first_name, last_name = random.choice(BRAZIL_BILLING_NAMES)
        line1, city, state, postal_code = random.choice(BRAZIL_BILLING_STREETS)
        suffix = random.randint(1000, 9999)
        payload = {
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
            "country": "BR",
            "line1": line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
        tax_id = normalize_buyer_tax_id(buyer_tax_id) or generate_random_cpf()
        payload["tax_id"] = tax_id
        return payload
    if normalized == "korea":
        suffix = random.randint(1000, 9999)
        return {
            "name": "Minjun Kim",
            "email": f"minjun.kim{suffix}@example.com",
            "country": "KR",
            "line1": "1 Teheran-ro",
            "city": "Seoul",
            "state": "Seoul",
            "postal_code": "06142",
        }
    if normalized == "swiss":
        suffix = random.randint(1000, 9999)
        return {
            "name": "Luca Meier",
            "email": f"luca.meier{suffix}@example.com",
            "country": "CH",
            "line1": "Bahnhofstrasse 1",
            "city": "Zurich",
            "state": "ZH",
            "postal_code": "8001",
        }
    if normalized == "ideal":
        suffix = random.randint(1000, 9999)
        return {
            "name": "Daan de Vries",
            "email": f"daan.devries{suffix}@example.com",
            "country": "NL",
            "line1": "Azalealaan 1196",
            "city": "Lutjebroek",
            "state": "NH",
            "postal_code": "1614SN",
        }
    if normalized == "upi":
        first_name, last_name = random.choice(INDIA_BILLING_NAMES)
        line1, city, state, postal_code = random.choice(INDIA_BILLING_STREETS)
        suffix = random.randint(1000, 9999)
        return {
            "name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
            "country": "IN",
            "line1": line1,
            "city": city,
            "state": state,
            "postal_code": postal_code,
        }
    first_name, last_name = random.choice(US_BILLING_NAMES)
    line1, city, state, postal_code = random.choice(US_BILLING_STREETS)
    suffix = random.randint(1000, 9999)
    return {
        "name": f"{first_name} {last_name}",
        "email": f"{first_name.lower()}.{last_name.lower()}{suffix}@example.com",
        "country": "US",
        "line1": line1,
        "city": city,
        "state": state,
        "postal_code": postal_code,
    }


def build_stripe_session(req: LongLinkRequest, proxy_override: str = "") -> Any:
    stripe = new_session()
    stripe.headers.update(
        {
            "User-Agent": req.user_agent.strip() or DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    if proxy_override:
        set_proxy_url(stripe, proxy_override)
    else:
        set_proxy(stripe, req.proxy, req.link_type)
    return stripe


def stripe_qr_page_payload(req: PixStatusRequest, pending: dict[str, Any]) -> dict[str, Any]:
    payment_page_url = str(
        pending.get("paymentPageUrl")
        or pending.get("pixHostedInstructionsUrl")
        or pending.get("providerRedirectUrl")
        or ""
    ).strip()
    if not payment_page_url:
        raise HTTPException(status_code=502, detail="payment page url missing")
    session = new_session()
    session.headers.update(
        {
            "User-Agent": req.user_agent.strip() or DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    preferred_proxy = str(pending.get("proxy") or req.proxy or "").strip()
    if preferred_proxy:
        set_proxy_url(session, preferred_proxy)
    response = session.get(payment_page_url, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"payment page fetch failed: http {response.status_code}")
    match = re.search(r'<meta id="payload" data-message="([^"]+)"', response.text or "")
    if not match:
        raise HTTPException(status_code=502, detail="payment page payload missing")
    raw_payload = match.group(1)
    try:
        padded = raw_payload + "=" * (-len(raw_payload) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"payment page payload decode failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="payment page payload invalid")
    return payload


def pix_state_from_page_payload(payload: dict[str, Any]) -> tuple[str, str]:
    raw_state = str(payload.get("intent_state") or "").strip().lower()
    if raw_state == "succeeded":
        return "succeeded", raw_state
    if raw_state in {"canceled", "cancelled"}:
        return "canceled", raw_state
    if raw_state == "expired":
        return "expired", raw_state
    if raw_state == "failed":
        return "failed", raw_state
    return "pending", raw_state or "pending"


def poll_pix_payment_status(req: PixStatusRequest) -> dict[str, Any]:
    cs_id = str(req.cs_id or "").strip()
    if not cs_id:
        raise HTTPException(status_code=400, detail="csId is required")

    pending = get_pix_pending_session(cs_id) or {}
    payload = stripe_qr_page_payload(req, pending)
    state, payment_object_status = pix_state_from_page_payload(payload)
    return_url = str((pending or {}).get("returnUrl") or "")
    mode = str((pending or {}).get("mode") or "")
    terminal = state in {"succeeded", "failed", "expired", "canceled"}
    zc_sync = ""
    if terminal and req.zc_base_url and req.claimed_account_id > 0:
        try:
            if state == "succeeded":
                zc_mark_payment_succeeded(
                    base_url=req.zc_base_url,
                    token=req.zc_token,
                    password=req.zc_password,
                    account_id=int(req.claimed_account_id or 0),
                    email=req.claimed_account_email,
                    claim_key=req.zc_claim_key,
                    payment_session_id=cs_id,
                    payment_channel="pix",
                )
                zc_sync = "payment_succeeded"
            elif state in {"failed", "expired", "canceled"}:
                zc_release_account(
                    ZCReleaseRequest(
                        baseUrl=req.zc_base_url,
                        token=req.zc_token,
                        password=req.zc_password,
                        claimKey=req.zc_claim_key,
                        accountId=int(req.claimed_account_id or 0),
                    )
                )
                zc_sync = "released"
        except Exception as exc:
            zc_sync = f"sync_error:{exc}"
    if terminal:
        existing = get_pix_pending_session(cs_id) or {}
        finished_at = current_timestamp()
        previous_state = str(existing.get("state") or "").strip().lower()
        if state == "succeeded" and previous_state != "succeeded":
            bump_stats(paid=True)
            log_event("pix.paid", "pix payment succeeded", cs_id=cs_id, status=state)
        if state in {"failed", "expired", "canceled"} and previous_state not in {"failed", "expired", "canceled"}:
            bump_stats(paid_failed=True)
            log_event("pix.failed", "pix payment ended without success", cs_id=cs_id, status=state)
        save_pix_pending_session(
            {
                **existing,
                "csId": cs_id,
                "proxy": existing.get("proxy") or req.proxy,
                "state": state,
                "paymentObjectStatus": payment_object_status,
                "returnUrl": return_url,
                "mode": mode,
                "zcSync": zc_sync,
                "finishedAt": finished_at,
                "nextCheckAt": 0,
                "removeAfter": finished_at + PIX_TERMINAL_DISPLAY_SECONDS,
            }
        )
    pending_after = enrich_pix_session_from_tasks(get_pix_pending_session(cs_id) or pending)
    return {
        "ok": True,
        "state": state,
        "payment_object_status": payment_object_status,
        "return_url": return_url,
        "mode": mode,
        "terminal": terminal,
        "zc_sync": zc_sync,
        "pix_qr_code": str((pending_after or {}).get("pixQrCode") or ""),
        "pix_qr_image_url_png": str((pending_after or {}).get("pixQrImageUrlPng") or ""),
        "pix_qr_image_url_svg": str((pending_after or {}).get("pixQrImageUrlSvg") or ""),
        "pix_hosted_instructions_url": str((pending_after or {}).get("pixHostedInstructionsUrl") or ""),
        "pix_expires_at": int((pending_after or {}).get("pixExpiresAt") or 0),
        "payment_page_url": str((pending_after or {}).get("paymentPageUrl") or ""),
        "raw": payload,
    }


def pix_status_request_from_item(item: dict[str, Any]) -> PixStatusRequest:
    return PixStatusRequest(
        cs_id=str(item.get("csId") or ""),
        stripe_publishable_key=str(item.get("stripePublishableKey") or ""),
        proxy=str(item.get("proxy") or ""),
        link_type=str(item.get("linkType") or "pix"),
        user_agent=str(item.get("userAgent") or ""),
        zc_base_url=str(item.get("zcBaseUrl") or ""),
        zc_token=str(item.get("zcToken") or ""),
        zc_password=str(item.get("zcPassword") or ""),
        zc_claim_key=str(item.get("zcClaimKey") or ""),
        claimed_account_id=int(item.get("claimedAccountId") or 0),
        claimed_account_email=str(item.get("claimedAccountEmail") or ""),
    )


def poll_pix_session_item(item: dict[str, Any]) -> dict[str, Any]:
    return poll_pix_payment_status(pix_status_request_from_item(item))


def stripe_create_payment_method(
    stripe: Any,
    cs_id: str,
    stripe_pk: str,
    billing: dict[str, str],
    payment_method_type: str,
    ctx: dict[str, Any],
) -> str:
    payment_method_type = normalize_provider_payment_method_type(payment_method_type)
    if payment_method_type == "gopay":
        runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
        body = {
            "billing_details[name]": billing.get("name") or "Budi Santoso",
            "billing_details[email]": billing.get("email") or "buyer@example.com",
            "billing_details[address][country]": billing.get("country") or "ID",
            "billing_details[address][line1]": billing.get("line1") or "Jl. Jend. Sudirman No. 1",
            "billing_details[address][city]": billing.get("city") or "Jakarta",
            "billing_details[address][postal_code]": billing.get("postal_code") or "10210",
            "billing_details[address][state]": billing.get("state") or "DKI Jakarta",
            "type": "gopay",
            "payment_user_agent": f"stripe.js/{runtime_version}; stripe-js-v3/{runtime_version}; payment-element; deferred-intent",
            "referrer": "https://chatgpt.com",
            "time_on_page": str(random.randint(25000, 55000)),
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "2021",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "guid": uuid.uuid4().hex,
            "muid": uuid.uuid4().hex,
            "sid": uuid.uuid4().hex,
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        }
    elif payment_method_type in {"gcash", "grabpay"}:
        body = {
            "billing_details[name]": billing.get("name") or "Miguel Santos",
            "billing_details[email]": billing.get("email") or "buyer@example.com",
            "billing_details[address][country]": billing.get("country") or "PH",
            "billing_details[address][line1]": billing.get("line1") or "6750 Ayala Avenue",
            "billing_details[address][city]": billing.get("city") or "Makati",
            "billing_details[address][postal_code]": billing.get("postal_code") or "1226",
            "billing_details[address][state]": billing.get("state") or "Metro Manila",
            "type": payment_method_type,
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "key": stripe_pk,
        }
    elif payment_method_type == "pix":
        runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
        body = {
            "billing_details[name]": billing.get("name") or "Joao Silva",
            "billing_details[email]": billing.get("email") or "buyer@example.com",
            "billing_details[address][country]": billing.get("country") or "BR",
            "billing_details[address][line1]": billing.get("line1") or "Avenida Paulista 1000",
            "billing_details[address][city]": billing.get("city") or "Sao Paulo",
            "billing_details[address][postal_code]": billing.get("postal_code") or "01310-100",
            "billing_details[address][state]": billing.get("state") or "SP",
            "type": "pix",
            "payment_user_agent": f"stripe.js/{runtime_version}; stripe-js-v3/{runtime_version}; payment-element; deferred-intent",
            "referrer": "https://chatgpt.com",
            "time_on_page": str(random.randint(25000, 55000)),
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "2021",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        }
        tax_id = str(billing.get("tax_id") or "").strip()
        if tax_id:
            body["billing_details[tax_id]"] = tax_id
    else:
        runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
        default_billing = {
            "paypal": {
                "name": "John Doe",
                "country": "US",
                "line1": "3110 Sunset Boulevard",
                "city": "Los Angeles",
                "postal_code": "90026",
                "state": "CA",
            },
            "kakao_pay": {
                "name": "Minjun Kim",
                "country": "KR",
                "line1": "1 Teheran-ro",
                "city": "Seoul",
                "postal_code": "06142",
                "state": "Seoul",
            },
            "twint": {
                "name": "Luca Meier",
                "country": "CH",
                "line1": "Bahnhofstrasse 1",
                "city": "Zurich",
                "postal_code": "8001",
                "state": "ZH",
            },
            "ideal": {
                "name": "Daan de Vries",
                "country": "NL",
                "line1": "Azalealaan 1196",
                "city": "Lutjebroek",
                "postal_code": "1614SN",
                "state": "NH",
            },
            "upi": {
                "name": "Aarav Sharma",
                "country": "IN",
                "line1": "12 MG Road",
                "city": "Bengaluru",
                "postal_code": "560001",
                "state": "KA",
            },
        }
        defaults = default_billing.get(payment_method_type, default_billing["paypal"])
        body = {
            "billing_details[name]": billing.get("name") or defaults["name"],
            "billing_details[email]": billing.get("email") or "buyer@example.com",
            "billing_details[address][country]": billing.get("country") or defaults["country"],
            "billing_details[address][line1]": billing.get("line1") or defaults["line1"],
            "billing_details[address][city]": billing.get("city") or defaults["city"],
            "billing_details[address][postal_code]": billing.get("postal_code") or defaults["postal_code"],
            "billing_details[address][state]": billing.get("state") or defaults["state"],
            "type": payment_method_type if payment_method_type in default_billing else "paypal",
            "payment_user_agent": f"stripe.js/{runtime_version}; stripe-js-v3/{runtime_version}; payment-element; deferred-intent",
            "referrer": "https://chatgpt.com",
            "time_on_page": str(random.randint(25000, 55000)),
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "2021",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        }
        if payment_method_type == "ideal":
            body["ideal[bank]"] = "bunq"
    response = stripe.post("https://api.stripe.com/v1/payment_methods", data=body, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=f"stripe payment_methods failed: {response.text[:500]}")
    pm_id = str((response.json() or {}).get("id") or "")
    if not pm_id.startswith("pm_"):
        raise HTTPException(status_code=502, detail=f"stripe payment_methods bad response: {response.text[:300]}")
    return pm_id


def stripe_confirm(
    stripe: Any,
    cs_id: str,
    pm_id: str,
    stripe_pk: str,
    payment_method_type: str,
    init_payload: dict[str, Any],
    ctx: dict[str, Any],
    checkout: dict[str, Any],
    req: LongLinkRequest,
    stripe_hosted_url: str,
    job_id: str = "",
) -> dict[str, Any]:
    payment_method_type = normalize_provider_payment_method_type(payment_method_type)
    trace_payment_method_type = payment_method_type
    return_url = stripe_confirm_return_url(cs_id, checkout, stripe_hosted_url)
    if payment_method_type == "gopay":
        init_checksum = stripe_init_gopay_checksum(stripe, cs_id, stripe_pk, req)
        runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
        body = {
            "guid": uuid.uuid4().hex,
            "muid": uuid.uuid4().hex,
            "sid": uuid.uuid4().hex,
            "payment_method": pm_id,
            "init_checksum": init_checksum,
            "version": runtime_version,
            "expected_amount": str(ctx.get("checkout_amount") or expected_amount(init_payload)),
            "expected_payment_method_type": payment_method_type,
            "return_url": return_url,
            "elements_session_client[session_id]": ctx["elements_session_id"],
            "elements_session_client[locale]": str(ctx.get("locale") or "en"),
            "elements_session_client[referrer_host]": "chatgpt.com",
            "elements_session_client[is_aggregation_expected]": "false",
            "elements_session_client[elements_init_source]": "custom_checkout",
            "elements_session_client[stripe_js_id]": ctx["stripe_js_id"],
            "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
            "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
            "elements_options_client[saved_payment_method][enable_save]": "never",
            "elements_options_client[saved_payment_method][enable_redisplay]": "never",
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "custom",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "consent[terms_of_service]": "accepted",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        }
    elif payment_method_type in {"gcash", "grabpay"}:
        init_checksum = stripe_init_gopay_checksum(stripe, cs_id, stripe_pk, req)
        body = {
            "guid": uuid.uuid4().hex,
            "muid": uuid.uuid4().hex,
            "sid": uuid.uuid4().hex,
            "payment_method": pm_id,
            "init_checksum": init_checksum,
            "version": "fed52f3bc6",
            "expected_amount": "0",
            "expected_payment_method_type": payment_method_type,
            "return_url": return_url,
            "elements_session_client[session_id]": f"elements_session_{uuid.uuid4().hex[:11]}",
            "elements_session_client[locale]": locale_parts(req.payment_locale)[1],
            "elements_session_client[referrer_host]": "chatgpt.com",
            "elements_session_client[is_aggregation_expected]": "false",
            "client_attribution_metadata[client_session_id]": str(uuid.uuid4()),
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "consent[terms_of_service]": "accepted",
            "key": stripe_pk,
        }
    else:
        runtime_version = str(ctx.get("runtime_version") or DEFAULT_STRIPE_RUNTIME_VERSION)
        expected_payment_method_type = payment_method_type if payment_method_type in {"pix", "paypal", "kakao_pay", "twint", "ideal", "upi"} else "paypal"
        body = {
            "guid": uuid.uuid4().hex,
            "muid": uuid.uuid4().hex,
            "sid": uuid.uuid4().hex,
            "payment_method": pm_id,
            "init_checksum": str(init_payload.get("init_checksum") or ctx.get("init_checksum") or ""),
            "version": runtime_version,
            "expected_amount": str(ctx.get("checkout_amount") or expected_amount(init_payload)),
            "expected_payment_method_type": expected_payment_method_type,
            "return_url": return_url,
            "elements_session_client[session_id]": ctx["elements_session_id"],
            "elements_session_client[locale]": str(ctx.get("locale") or "en"),
            "elements_session_client[referrer_host]": "chatgpt.com",
            "elements_session_client[is_aggregation_expected]": "false",
            "elements_session_client[elements_init_source]": "custom_checkout",
            "elements_session_client[stripe_js_id]": ctx["stripe_js_id"],
            "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
            "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
            "elements_options_client[saved_payment_method][enable_save]": "never",
            "elements_options_client[saved_payment_method][enable_redisplay]": "never",
            "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
            "client_attribution_metadata[checkout_session_id]": cs_id,
            "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
            "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
            "client_attribution_metadata[elements_session_config_id]": ctx["elements_session_config_id"],
            "client_attribution_metadata[merchant_integration_source]": "checkout",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "custom",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "automatic",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
            "consent[terms_of_service]": "accepted",
            "key": stripe_pk,
            "_stripe_version": STRIPE_VERSION_FULL,
        }
    response = stripe.post(f"https://api.stripe.com/v1/payment_pages/{cs_id}/confirm", data=body, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 400:
        log_protocol_capture(
            "protocol.stripe_confirm",
            "stripe confirm error",
            job_id=job_id,
            cs_id=cs_id,
            status="failed",
            response=response,
            extras=(
                f"pm_type={trace_payment_method_type}",
                f"body={event_field_text(response.text, limit=240)}",
            ),
        )
        raise HTTPException(status_code=response.status_code, detail=f"stripe confirm failed: {response.text[:500]}")
    try:
        payload = response.json() or {}
    except Exception as exc:
        log_protocol_capture(
            "protocol.stripe_confirm",
            "stripe confirm invalid json",
            job_id=job_id,
            cs_id=cs_id,
            status="failed",
            response=response,
            extras=(
                f"pm_type={trace_payment_method_type}",
                f"body={event_field_text(response.text, limit=240)}",
            ),
        )
        raise HTTPException(status_code=502, detail=f"stripe confirm bad response: {response.text[:300]}") from exc
    log_stripe_confirm_success(
        response,
        payload,
        body,
        trace_payment_method_type,
        job_id=job_id,
        cs_id=cs_id,
    )
    return payload


def extract_redirect_to_url(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("type") == "redirect_to_url":
        redirect_to_url = next_action.get("redirect_to_url") or {}
        if isinstance(redirect_to_url, dict):
            url = str(redirect_to_url.get("url") or "").strip()
            if url:
                return url
    for key in ("setup_intent", "payment_intent"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = extract_redirect_to_url(nested)
            if found:
                return found
    payment_method_object = payload.get("payment_method_object")
    if isinstance(payment_method_object, dict):
        found = extract_redirect_to_url(payment_method_object)
        if found:
            return found
    return ""


def extract_pix_details(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("type") == "pix_display_qr_code":
        pix_display = next_action.get("pix_display_qr_code") or {}
        if isinstance(pix_display, dict):
            expires_raw = pix_display.get("expires_at")
            try:
                expires_at = int(expires_raw or 0)
            except Exception:
                expires_at = 0
            return {
                "pix_hosted_instructions_url": str(pix_display.get("hosted_instructions_url") or "").strip(),
                "pix_qr_code": str(pix_display.get("data") or pix_display.get("qr_code") or "").strip(),
                "pix_qr_image_url_png": str(pix_display.get("image_url_png") or "").strip(),
                "pix_qr_image_url_svg": str(pix_display.get("image_url_svg") or "").strip(),
                "pix_expires_at": expires_at,
            }
    for key in ("setup_intent", "payment_intent"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = extract_pix_details(nested)
            if found:
                return found
    payment_method_object = payload.get("payment_method_object")
    if isinstance(payment_method_object, dict):
        found = extract_pix_details(payment_method_object)
        if found:
            return found
    return {}


def parse_expires_at(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def extract_upi_qr_details(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    next_action = payload.get("next_action")
    if isinstance(next_action, dict):
        details = extract_upi_qr_next_action(next_action)
        if details:
            return details
    for key in ("setup_intent", "payment_intent"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = extract_upi_qr_details(nested)
            if found:
                return found
    payment_method_object = payload.get("payment_method_object")
    if isinstance(payment_method_object, dict):
        found = extract_upi_qr_details(payment_method_object)
        if found:
            return found
    return {}


def extract_upi_qr_next_action(next_action: dict[str, Any]) -> dict[str, Any]:
    action_type = str(next_action.get("type") or "").strip()
    if action_type and action_type not in {
        "upi_display_qr_code",
        "display_upi_qr_code",
        "display_qr_code",
        "upi_handle_redirect_or_display_qr_code",
    }:
        return {}
    if action_type == "upi_handle_redirect_or_display_qr_code":
        handle_payload = next_action.get("upi_handle_redirect_or_display_qr_code")
        if isinstance(handle_payload, dict):
            qr_code = handle_payload.get("qr_code")
            if isinstance(qr_code, dict):
                details = normalize_upi_qr_display(qr_code)
                if details:
                    hosted_url = str(handle_payload.get("hosted_instructions_url") or "").strip()
                    if hosted_url:
                        details["upi_hosted_url"] = hosted_url
                    return details
            details = normalize_upi_qr_display(handle_payload)
            if details:
                return details
    for key in ("upi_display_qr_code", "display_upi_qr_code", "display_qr_code", "qr_code"):
        display = next_action.get(key)
        if isinstance(display, dict):
            details = normalize_upi_qr_display(display)
            if details:
                return details
    details = normalize_upi_qr_display(next_action)
    if details:
        return details
    return {}


def extract_upi_success_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    qr_details = extract_upi_qr_details(payload)
    if qr_details:
        return {
            "next_action_type": str((payload.get("next_action") or {}).get("type") or "").strip(),
            "upi_redirect_url": "",
            "upi_qr_data": str(qr_details.get("provider_qr_url") or "").strip(),
            "upi_qr_image_url": str(qr_details.get("provider_qr_image_url") or "").strip(),
            "upi_hosted_url": str(qr_details.get("upi_hosted_url") or qr_details.get("provider_qr_image_url") or "").strip(),
            "provider_qr_url": str(qr_details.get("provider_qr_url") or "").strip(),
            "provider_qr_svg": str(qr_details.get("provider_qr_svg") or ""),
            "provider_qr_image_url": str(qr_details.get("provider_qr_image_url") or "").strip(),
            "provider_expires_at": int(qr_details.get("provider_expires_at") or 0),
        }
    redirect_url = extract_redirect_to_url(payload)
    if redirect_url:
        return {
            "next_action_type": "redirect_to_url",
            "upi_redirect_url": redirect_url,
            "upi_qr_data": "",
            "upi_qr_image_url": "",
            "upi_hosted_url": redirect_url,
            "provider_redirect_url": redirect_url,
        }
    return {}


def normalize_upi_qr_display(display: dict[str, Any]) -> dict[str, Any]:
    qr_value = str(display.get("data") or display.get("qr_code") or display.get("url") or "").strip()
    hosted_url = str(display.get("hosted_instructions_url") or "").strip()
    image_url = str(
        display.get("image_url_png")
        or display.get("image_url")
        or display.get("image_url_utf8")
        or display.get("image_url_uri")
        or ""
    ).strip()
    image_svg = str(display.get("image_url_svg") or display.get("svg") or "").strip()
    if not qr_value and not image_url and not image_svg and not hosted_url:
        return {}
    qr_svg = ""
    if qr_value:
        qr_svg = render_qr_svg(qr_value)
    return {
        "provider_qr_url": qr_value or image_url or image_svg,
        "provider_qr_svg": qr_svg,
        "provider_qr_image_url": image_url or image_svg,
        "provider_expires_at": parse_expires_at(display.get("expires_at")),
        "upi_hosted_url": hosted_url,
    }


def find_setup_intent(data: dict[str, Any]) -> dict[str, Any] | None:
    setup_intent = data.get("setup_intent")
    if isinstance(setup_intent, dict):
        return setup_intent
    payment_method_object = data.get("payment_method_object")
    if isinstance(payment_method_object, dict):
        candidate = payment_method_object.get("setup_intent")
        if isinstance(candidate, dict):
            return candidate
    try:
        raw = json.dumps(data, ensure_ascii=False)
    except Exception:
        raw = str(data or "")
    match = re.search(r"seti_[A-Za-z0-9]+", raw)
    if match:
        return {"id": match.group(0)}
    return None


def stripe_payment_page_redirect_url(stripe: Any, cs_id: str, stripe_pk: str, req: LongLinkRequest, timeout_seconds: float = 30) -> str:
    deadline = time.time() + max(1.0, float(timeout_seconds or 30))
    last_err = ""
    params = {
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
    }
    while time.time() < deadline:
        response = stripe.get(f"https://api.stripe.com/v1/payment_pages/{cs_id}", params=params, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            payload = response.json() or {}
            terminal_failure = payment_page_terminal_failure(payload)
            if terminal_failure:
                raise HTTPException(status_code=502, detail=f"provider payment failed: {terminal_failure}")
            redirect_url = extract_redirect_to_url(payload)
            if redirect_url:
                return redirect_url
            setup_intent = find_setup_intent(payload)
            if isinstance(setup_intent, dict):
                redirect_url = extract_redirect_to_url(setup_intent)
                if redirect_url:
                    return redirect_url
            submission_state = str((payload.get("submission_attempt") or {}).get("state") or "").strip()
            last_err = f"state={submission_state or '-'} keys=[{','.join(sorted(payload.keys())[:8])}]"
        else:
            last_err = f"http {response.status_code}: {response.text[:120]}"
        time.sleep(1)
    raise HTTPException(status_code=504, detail=f"redirect url resolution timeout: {last_err}")


def stripe_payment_page_pix_details(
    stripe: Any,
    cs_id: str,
    stripe_pk: str,
    req: LongLinkRequest,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    deadline = time.time() + max(1.0, float(timeout_seconds or 30))
    last_err = ""
    params = {
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
    }
    while time.time() < deadline:
        response = stripe.get(f"https://api.stripe.com/v1/payment_pages/{cs_id}", params=params, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            payload = response.json() or {}
            terminal_failure = payment_page_terminal_failure(payload)
            if terminal_failure:
                raise HTTPException(status_code=502, detail=f"pix payment failed: {terminal_failure}")
            pix_details = extract_pix_details(payload)
            if pix_details:
                return pix_details
            setup_intent = find_setup_intent(payload)
            if isinstance(setup_intent, dict):
                pix_details = extract_pix_details(setup_intent)
                if pix_details:
                    return pix_details
            submission_state = str((payload.get("submission_attempt") or {}).get("state") or "").strip()
            last_err = f"state={submission_state or '-'} keys=[{','.join(sorted(payload.keys())[:8])}]"
        else:
            last_err = f"http {response.status_code}: {response.text[:120]}"
        time.sleep(1)
    raise HTTPException(status_code=504, detail=f"pix qr resolution timeout: {last_err}")


def stripe_payment_page_upi_details(
    stripe: Any,
    cs_id: str,
    stripe_pk: str,
    req: LongLinkRequest,
    job_id: str = "",
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    deadline = time.time() + max(1.0, float(timeout_seconds or 30))
    last_err = ""
    params = {
        "key": stripe_pk,
        "_stripe_version": STRIPE_VERSION_FULL,
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
    }
    log_protocol_capture(
        "protocol.upi_qr_resolution",
        "payment_page qr resolution start",
        job_id=job_id,
        cs_id=cs_id,
        status="pending",
        extras=("strategy=payment_page",),
    )
    while time.time() < deadline:
        response = stripe.get(f"https://api.stripe.com/v1/payment_pages/{cs_id}", params=params, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            payload = response.json() or {}
            terminal_failure = payment_page_terminal_failure(payload)
            if terminal_failure:
                log_protocol_capture(
                    "protocol.upi_qr_resolution",
                    "payment_page terminal failure",
                    job_id=job_id,
                    cs_id=cs_id,
                    status="failed",
                    response=response,
                    payload=payload,
                    extras=(terminal_failure,),
                )
                raise HTTPException(status_code=502, detail=f"upi payment failed: {terminal_failure}")
            upi_result = extract_upi_success_result(payload)
            if upi_result:
                log_protocol_capture(
                    "protocol.upi_qr_resolution",
                    "payment_page qr resolved",
                    job_id=job_id,
                    cs_id=cs_id,
                    status="ok",
                    response=response,
                    payload=payload,
                    extras=("strategy=payment_page",),
                )
                return upi_result
            setup_intent = find_setup_intent(payload)
            if isinstance(setup_intent, dict):
                upi_result = extract_upi_success_result(setup_intent)
                if upi_result:
                    log_protocol_capture(
                        "protocol.upi_qr_resolution",
                        "payment_page qr resolved",
                        job_id=job_id,
                        cs_id=cs_id,
                        status="ok",
                        response=response,
                        payload=payload,
                        extras=("strategy=payment_page",),
                    )
                    return upi_result
            submission_state = str((payload.get("submission_attempt") or {}).get("state") or "").strip()
            last_err = f"state={submission_state or '-'} keys=[{','.join(sorted(payload.keys())[:8])}]"
        else:
            last_err = f"http {response.status_code}: {response.text[:120]}"
        time.sleep(1)
    raise HTTPException(status_code=504, detail=f"upi qr resolution timeout: {last_err}")


def chatgpt_approve(chatgpt: Any, cs_id: str, checkout: dict[str, Any], job_id: str = "") -> None:
    country = checkout["billing_country"]
    processor_entity = processor_entity_for_country(country, checkout.get("processor_entity", ""))
    try:
        chatgpt.post(
            "https://chatgpt.com/backend-api/sentinel/ping",
            json={},
            headers={
                "Referer": "https://chatgpt.com/",
                "x-openai-target-path": "/backend-api/sentinel/ping",
                "x-openai-target-route": "/backend-api/sentinel/ping",
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        pass
    response = chatgpt.post(
        "https://chatgpt.com/backend-api/payments/checkout/approve",
        json={"checkout_session_id": cs_id, "processor_entity": processor_entity},
        headers={
            "Referer": f"https://chatgpt.com/checkout/{processor_entity}/{cs_id}",
            "x-openai-target-path": "/backend-api/payments/checkout/approve",
            "x-openai-target-route": "/backend-api/payments/checkout/approve",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        log_protocol_capture(
            "protocol.chatgpt_approve",
            "approve error",
            job_id=job_id,
            cs_id=cs_id,
            status="failed",
            response=response,
            extras=(
                f"processor_entity={processor_entity}",
                f"body={event_field_text(response.text, limit=240)}",
            ),
        )
        raise HTTPException(status_code=response.status_code, detail=f"chatgpt approve failed: {response.text[:500]}")
    response_payload: dict[str, Any] = {}
    try:
        response_payload = response.json() or {}
    except Exception:
        response_payload = {}
    result = str(response_payload.get("result") or "").strip()
    log_protocol_capture(
        "protocol.chatgpt_approve",
        "approve response",
        job_id=job_id,
        cs_id=cs_id,
        status="ok" if result == "approved" else "failed",
        response=response,
        payload=response_payload,
        extras=(
            f"processor_entity={processor_entity}",
            f"result={result or '-'}",
            f"body={event_field_text(response_payload or response.text, limit=240)}",
        ),
    )
    if result != "approved":
        raise HTTPException(status_code=502, detail=f"chatgpt approve unexpected result: {result!r}")


def chatgpt_approve_result(chatgpt: Any, cs_id: str, checkout: dict[str, Any], job_id: str = "") -> str:
    country = checkout["billing_country"]
    processor_entity = processor_entity_for_country(country, checkout.get("processor_entity", ""))
    try:
        chatgpt.post(
            "https://chatgpt.com/backend-api/sentinel/ping",
            json={},
            headers={
                "Referer": "https://chatgpt.com/",
                "x-openai-target-path": "/backend-api/sentinel/ping",
                "x-openai-target-route": "/backend-api/sentinel/ping",
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        pass
    response = chatgpt.post(
        "https://chatgpt.com/backend-api/payments/checkout/approve",
        json={"checkout_session_id": cs_id, "processor_entity": processor_entity},
        headers={
            "Referer": f"https://chatgpt.com/checkout/{processor_entity}/{cs_id}",
            "x-openai-target-path": "/backend-api/payments/checkout/approve",
            "x-openai-target-route": "/backend-api/payments/checkout/approve",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        log_protocol_capture(
            "protocol.chatgpt_approve",
            "approve error",
            job_id=job_id,
            cs_id=cs_id,
            status="failed",
            response=response,
            extras=(
                f"processor_entity={processor_entity}",
                f"body={event_field_text(response.text, limit=240)}",
            ),
        )
        raise HTTPException(status_code=response.status_code, detail=f"chatgpt approve failed: {response.text[:500]}")
    response_payload: dict[str, Any] = {}
    try:
        response_payload = response.json() or {}
    except Exception:
        response_payload = {}
    result = str(response_payload.get("result") or "").strip()
    status = "ok" if result == "approved" else ("pending" if result else "failed")
    log_protocol_capture(
        "protocol.chatgpt_approve",
        "approve response",
        job_id=job_id,
        cs_id=cs_id,
        status=status,
        response=response,
        payload=response_payload,
        extras=(
            f"processor_entity={processor_entity}",
            f"result={result or '-'}",
            f"body={event_field_text(response_payload or response.text, limit=240)}",
        ),
    )
    if not result:
        raise HTTPException(status_code=502, detail="chatgpt approve missing result")
    return result


def chatgpt_approve_pool(
    chatgpt: Any,
    cs_id: str,
    checkout: dict[str, Any],
    *,
    pool_keep: int,
    pool_max: int,
    job_id: str = "",
) -> str:
    keep = max(1, min(50, int(pool_keep or 1)))
    max_attempts = max(1, min(2000, int(pool_max or keep)))
    blocked = 0
    other = 0
    for attempt in range(1, max_attempts + 1):
        try:
            result = chatgpt_approve_result(chatgpt, cs_id, checkout, job_id=job_id)
        except HTTPException as exc:
            detail = progress_error_text(exc).lower()
            if "blocked" in detail:
                blocked += 1
            else:
                other += 1
            result = ""
        if result == "approved":
            log_protocol_capture(
                "protocol.approval_gate",
                "approve-hit",
                job_id=job_id,
                cs_id=cs_id,
                status="ok",
                extras=(f"slot={attempt}", f"pool_keep={keep}", f"pool_max={max_attempts}"),
            )
            return "approved"
        if attempt % 50 == 0 or attempt == max_attempts:
            log_protocol_capture(
                "protocol.approval_gate",
                "approve-tick",
                job_id=job_id,
                cs_id=cs_id,
                status="pending",
                extras=(
                    f"slot={attempt}",
                    f"max={max_attempts}",
                    f"blocked={blocked}",
                    f"other={other}",
                ),
            )
    raise HTTPException(status_code=502, detail="approve blocked")


def redirect_url_after_confirm(
    chatgpt: Any,
    stripe: Any,
    confirm_payload: dict[str, Any],
    cs_id: str,
    stripe_pk: str,
    checkout: dict[str, Any],
    req: LongLinkRequest,
    job_id: str = "",
) -> str:
    submission = confirm_payload.get("submission_attempt") if isinstance(confirm_payload, dict) else None
    redirect_url = extract_redirect_to_url(confirm_payload)
    if redirect_url:
        return redirect_url
    setup_intent = find_setup_intent(confirm_payload) if isinstance(confirm_payload, dict) else None
    if isinstance(setup_intent, dict):
        redirect_url = extract_redirect_to_url(setup_intent)
        if redirect_url:
            return redirect_url
    if isinstance(submission, dict) and submission.get("state") == "requires_approval":
        log_protocol_capture(
            "protocol.approval_gate",
            "submission requires approval",
            job_id=job_id,
            cs_id=cs_id,
            status="pending",
            payload=confirm_payload,
            extras=(confirm_payload_summary(confirm_payload),),
        )
        chatgpt_approve(chatgpt, cs_id, checkout, job_id=job_id)
        return stripe_payment_page_redirect_url(
            stripe,
            cs_id,
            stripe_pk,
            req,
            timeout_seconds=90 if normalize_link_type(req.link_type) in WALLET_APPROVAL_LINE_CONFIG else 45,
        )
    return stripe_payment_page_redirect_url(
        stripe,
        cs_id,
        stripe_pk,
        req,
        timeout_seconds=60 if normalize_link_type(req.link_type) in WALLET_APPROVAL_LINE_CONFIG else 30,
    )


def pix_details_after_confirm(
    chatgpt: Any,
    stripe: Any,
    confirm_payload: dict[str, Any],
    cs_id: str,
    stripe_pk: str,
    checkout: dict[str, Any],
    req: LongLinkRequest,
) -> dict[str, Any]:
    submission = confirm_payload.get("submission_attempt") if isinstance(confirm_payload, dict) else None
    pix_details = extract_pix_details(confirm_payload)
    if pix_details:
        return pix_details
    setup_intent = find_setup_intent(confirm_payload) if isinstance(confirm_payload, dict) else None
    if isinstance(setup_intent, dict):
        pix_details = extract_pix_details(setup_intent)
        if pix_details:
            return pix_details
    if isinstance(submission, dict) and submission.get("state") == "requires_approval":
        chatgpt_approve(chatgpt, cs_id, checkout)
        return stripe_payment_page_pix_details(stripe, cs_id, stripe_pk, req, timeout_seconds=45)
    return stripe_payment_page_pix_details(stripe, cs_id, stripe_pk, req, timeout_seconds=30)


def upi_details_after_confirm(
    chatgpt: Any,
    stripe: Any,
    confirm_payload: dict[str, Any],
    cs_id: str,
    stripe_pk: str,
    checkout: dict[str, Any],
    req: LongLinkRequest,
    job_id: str = "",
    pool_keep: int = 1,
    pool_max: int = 1,
) -> dict[str, Any]:
    submission = confirm_payload.get("submission_attempt") if isinstance(confirm_payload, dict) else None
    upi_result = extract_upi_success_result(confirm_payload)
    if upi_result:
        return upi_result
    if isinstance(submission, dict) and submission.get("state") == "requires_approval":
        log_protocol_capture(
            "protocol.approval_gate",
            "submission requires approval",
            job_id=job_id,
            cs_id=cs_id,
            status="pending",
            payload=confirm_payload,
            extras=(confirm_payload_summary(confirm_payload),),
        )
        chatgpt_approve_pool(
            chatgpt,
            cs_id,
            checkout,
            pool_keep=pool_keep,
            pool_max=pool_max,
            job_id=job_id,
        )
        return stripe_payment_page_upi_details(
            stripe,
            cs_id,
            stripe_pk,
            req,
            job_id=job_id,
            timeout_seconds=45,
        )
    return stripe_payment_page_upi_details(stripe, cs_id, stripe_pk, req, job_id=job_id, timeout_seconds=30)


def resolve_external_redirect(stripe: Any, redirect_url: str, preferred_hosts: tuple[str, ...] = (), max_hops: int = 5) -> str:
    current = str(redirect_url or "").strip()
    preferred = tuple(host.lower().lstrip(".") for host in preferred_hosts if host)
    for _ in range(max(1, int(max_hops or 1))):
        if not current:
            return ""
        host = (urlsplit(current).netloc or "").lower()
        if preferred and any(host == item or host.endswith(f".{item}") for item in preferred):
            return current
        try:
            response = stripe.get(current, allow_redirects=False, timeout=DEFAULT_TIMEOUT)
        except Exception:
            return current
        if response.status_code not in (301, 302, 303, 307, 308):
            return current
        location = str(response.headers.get("Location") or "").strip()
        if not location:
            return current
        current = urljoin(current, location)
    return current


def preferred_hosts_for_link_type(link_type: str) -> tuple[str, ...]:
    normalized = normalize_link_type(link_type)
    if normalized == "paypal":
        return ("paypal.com",)
    if normalized == "gopay":
        return ("gopay.co.id", "gojek.com", "midtrans.com")
    if normalized == "gcash":
        return ("gcash.com",)
    if normalized == "grabpay":
        return ("grab.com", "grabpay.com")
    if normalized == "korea":
        return ("kakaopay.com",)
    if normalized == "swiss":
        return ("twint.ch",)
    if normalized == "ideal":
        return ("ideal.nl",)
    if normalized == "upi":
        return ("stripe.com", "hooks.stripe.com")
    return ()


def create_provider_payment_state(stripe: Any, checkout: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    req = options["req"]
    link_type = str(options["link_type"])
    stripe_pk = str(options["stripe_pk"])
    ctx = stripe_context(checkout["cs_id"], options["init_payload"], req)
    billing = billing_for_link_type(link_type, req.buyer_tax_id)
    pm_id = stripe_create_payment_method(stripe, checkout["cs_id"], stripe_pk, billing, link_type, ctx)
    confirm_payload = stripe_confirm(
        stripe,
        checkout["cs_id"],
        pm_id,
        stripe_pk,
        link_type,
        options["init_payload"],
        ctx,
        checkout,
        req,
        str(options.get("stripe_hosted_url") or ""),
        job_id=str(options.get("job_id") or ""),
    )
    return {
        "confirm_payload": confirm_payload,
        "cs_id": checkout["cs_id"],
        "job_id": str(options.get("job_id") or ""),
        "link_type": link_type,
        "pm_id": pm_id,
        "stripe_pk": stripe_pk,
        "pool_keep": int(options.get("pool_keep") or 1),
        "pool_max": int(options.get("pool_max") or 1),
    }


def build_pix_provider_fields(pm_id: str, checkout: dict[str, Any], pix_details: dict[str, Any]) -> dict[str, Any]:
    hosted_url = str(pix_details.get("pix_hosted_instructions_url") or "").strip()
    image_url_png = str(pix_details.get("pix_qr_image_url_png") or "").strip()
    image_url_svg = str(pix_details.get("pix_qr_image_url_svg") or "").strip()
    checkout_url = str(checkout.get("checkout_url") or "").strip()
    return {
        "payment_method_id": pm_id,
        "stripe_redirect_url": "",
        "provider_redirect_url": hosted_url,
        "long_url": hosted_url or checkout_url,
        "pix_hosted_instructions_url": hosted_url,
        "pix_qr_code": str(pix_details.get("pix_qr_code") or "").strip(),
        "pix_qr_image_url_png": image_url_png,
        "pix_qr_image_url_svg": image_url_svg,
        "pix_expires_at": int(pix_details.get("pix_expires_at") or 0),
    }


def build_upi_provider_fields(pm_id: str, checkout: dict[str, Any], upi_details: dict[str, Any]) -> dict[str, Any]:
    qr_url = str(upi_details.get("provider_qr_url") or "").strip()
    qr_image_url = str(upi_details.get("provider_qr_image_url") or "").strip()
    display_url = qr_url or qr_image_url
    redirect_url = str(upi_details.get("provider_redirect_url") or upi_details.get("upi_redirect_url") or "").strip()
    hosted_url = str(upi_details.get("upi_hosted_url") or redirect_url or "").strip()
    checkout_url = str(checkout.get("checkout_url") or "").strip()
    return {
        "payment_method_id": pm_id,
        "stripe_redirect_url": "",
        "provider_redirect_url": redirect_url,
        "long_url": hosted_url or checkout_url,
        "provider_qr_url": display_url,
        "provider_qr_svg": str(upi_details.get("provider_qr_svg") or ""),
        "provider_expires_at": int(upi_details.get("provider_expires_at") or 0),
        "pix_hosted_instructions_url": "",
        "pix_qr_code": "",
        "pix_qr_image_url_png": "",
        "pix_qr_image_url_svg": "",
        "pix_expires_at": 0,
        "next_action_type": str(upi_details.get("next_action_type") or "").strip(),
        "upi_qr_image_url": qr_image_url,
        "upi_hosted_url": hosted_url,
        "upi_qr_data": qr_url,
    }


def build_redirect_provider_fields(pm_id: str, stripe_redirect_url: str, provider_url: str) -> dict[str, Any]:
    return {
        "payment_method_id": pm_id,
        "stripe_redirect_url": stripe_redirect_url,
        "provider_redirect_url": provider_url,
        "long_url": provider_url or stripe_redirect_url,
        "pix_hosted_instructions_url": "",
        "pix_qr_code": "",
        "pix_qr_image_url_png": "",
        "pix_qr_image_url_svg": "",
        "pix_expires_at": 0,
    }


def resolve_pix_provider_fields(state: dict[str, Any], checkout: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    pix_details = pix_details_after_confirm(
        deps["chatgpt"],
        deps["stripe"],
        state["confirm_payload"],
        state["cs_id"],
        state["stripe_pk"],
        checkout,
        deps["req"],
    )
    return build_pix_provider_fields(state["pm_id"], checkout, pix_details)


def resolve_upi_provider_fields(state: dict[str, Any], checkout: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    upi_details = upi_details_after_confirm(
        deps["chatgpt"],
        deps["stripe"],
        state["confirm_payload"],
        state["cs_id"],
        state["stripe_pk"],
        checkout,
        deps["req"],
        job_id=state["job_id"],
        pool_keep=int(state.get("pool_keep") or 1),
        pool_max=int(state.get("pool_max") or 1),
    )
    return build_upi_provider_fields(state["pm_id"], checkout, upi_details)


def resolve_redirect_provider_fields(state: dict[str, Any], checkout: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    stripe_redirect_url = redirect_url_after_confirm(
        deps["chatgpt"],
        deps["stripe"],
        state["confirm_payload"],
        state["cs_id"],
        state["stripe_pk"],
        checkout,
        deps["req"],
        job_id=state["job_id"],
    )
    preferred_hosts = preferred_hosts_for_link_type(state["link_type"])
    provider_url = resolve_external_redirect(deps["stripe"], stripe_redirect_url, preferred_hosts=preferred_hosts)
    return build_redirect_provider_fields(state["pm_id"], stripe_redirect_url, provider_url)


def resolve_gopay_approval_fields(state: dict[str, Any], checkout: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    confirm_payload = state["confirm_payload"] if isinstance(state["confirm_payload"], dict) else {}
    submission = confirm_payload.get("submission_attempt") if isinstance(confirm_payload, dict) else None
    submission_state = str((submission or {}).get("state") or "").strip()
    stripe_redirect_url = ""
    if submission_state == "requires_approval":
        log_protocol_capture(
            "protocol.approval_gate",
            "submission requires approval",
            job_id=state["job_id"],
            cs_id=state["cs_id"],
            status="pending",
            payload=confirm_payload,
            extras=(confirm_payload_summary(confirm_payload),),
        )
        approval_result = chatgpt_approve_result(
            deps["chatgpt"],
            state["cs_id"],
            checkout,
            job_id=state["job_id"],
        )
        if approval_result != "approved":
            raise HTTPException(status_code=502, detail=f"provider approval did not succeed: {approval_result!r}")
        if normalize_link_type(state["link_type"]) == "ideal":
            time.sleep(2)
        stripe_redirect_url = stripe_payment_page_redirect_url(
            deps["stripe"],
            state["cs_id"],
            state["stripe_pk"],
            deps["req"],
            timeout_seconds=90,
        )
    else:
        stripe_redirect_url = redirect_url_after_confirm(
            deps["chatgpt"],
            deps["stripe"],
            confirm_payload,
            state["cs_id"],
            state["stripe_pk"],
            checkout,
            deps["req"],
            job_id=state["job_id"],
        )
    if normalize_link_type(state["link_type"]) == "ideal":
        fields = build_redirect_provider_fields(state["pm_id"], stripe_redirect_url, stripe_redirect_url)
        if submission_state == "requires_approval":
            fields["approval_result"] = "approved"
            fields["submission_state"] = submission_state
            fields["completion_stage"] = "provider_redirect_ready"
        return fields
    preferred_hosts = preferred_hosts_for_link_type(state["link_type"])
    provider_url = resolve_external_redirect(deps["stripe"], stripe_redirect_url, preferred_hosts=preferred_hosts)
    if not provider_url:
        raise HTTPException(status_code=502, detail="provider redirect missing after approval")
    provider_host = (urlsplit(provider_url).netloc or "").lower()
    if not any(provider_host == host or provider_host.endswith(f".{host}") for host in preferred_hosts):
        raise HTTPException(status_code=502, detail=f"provider redirect host mismatch: {provider_url[:200]}")
    fields = build_redirect_provider_fields(state["pm_id"], stripe_redirect_url, provider_url)
    if submission_state == "requires_approval":
        fields["approval_result"] = "approved"
        fields["submission_state"] = submission_state
        fields["completion_stage"] = "provider_redirect_ready"
    return fields


def resolve_wallet_approval_fields(state: dict[str, Any], checkout: dict[str, Any], deps: dict[str, Any]) -> dict[str, Any]:
    return resolve_gopay_approval_fields(state, checkout, deps)


def create_provider_link(
    chatgpt: Any,
    checkout: dict[str, Any],
    init_payload: dict[str, Any],
    stripe_hosted_url: str,
    req: LongLinkRequest,
    provider_proxy: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    link_type = normalize_link_type(req.link_type)
    stripe_pk = str(checkout.get("publishable_key") or "").strip() or req.stripe_publishable_key.strip() or DEFAULT_STRIPE_PK
    stripe = build_stripe_session(req, proxy_override=provider_proxy)
    state = create_provider_payment_state(
        stripe,
        checkout,
        {
            "init_payload": init_payload,
            "job_id": job_id,
            "link_type": link_type,
            "pool_keep": int(getattr(req, "pool_keep", 1) or 1),
            "pool_max": int(getattr(req, "pool_max", 1) or 1),
            "req": req,
            "stripe_hosted_url": stripe_hosted_url,
            "stripe_pk": stripe_pk,
        },
    )
    deps = {"chatgpt": chatgpt, "req": req, "stripe": stripe}
    if link_type == "pix":
        return resolve_pix_provider_fields(state, checkout, deps)
    if link_type == "upi":
        return resolve_upi_provider_fields(state, checkout, deps)
    if link_type in WALLET_APPROVAL_LINE_CONFIG or link_type == "ideal":
        return resolve_wallet_approval_fields(state, checkout, deps)
    return resolve_redirect_provider_fields(state, checkout, deps)


def upi_request_to_long_link(req: UpiApiRequest, job_id: str) -> LongLinkRequest:
    long_link = LongLinkRequest(
        accessToken=req.token,
        link_type="upi",
        billing_country="IN",
        payment_locale="en",
        job_id=job_id,
        autoClaimZc=False,
    )
    setattr(long_link, "pool_keep", max(1, min(50, int(req.pool_keep or UPI_DEFAULT_POOL_KEEP))))
    setattr(long_link, "pool_max", max(1, min(2000, int(req.pool_max or UPI_DEFAULT_POOL_MAX))))
    setattr(long_link, "promo_id", str(req.promo_id or "plus-1-month-free").strip() or "plus-1-month-free")
    long_link.use_promo_params = bool(getattr(long_link, "promo_id", ""))
    return long_link


def upi_response_from_long_link(result: LongLinkResponse, *, request_id: str, duration_ms: int) -> UpiApiResponse:
    upi_redirect_url = str(result.provider_redirect_url or "").strip()
    raw_qr_value = str(result.provider_qr_url or result.upi_qr_data or "").strip()
    upi_qr_image_url = str(result.upi_qr_image_url or "").strip()
    upi_qr_data = str(result.upi_qr_data or "").strip()
    if raw_qr_value.startswith(("http://", "https://")):
        upi_qr_image_url = upi_qr_image_url or raw_qr_value
        if upi_qr_data == raw_qr_value:
            upi_qr_data = ""
    elif raw_qr_value and not upi_qr_data:
        upi_qr_data = raw_qr_value
    next_action_type = str(result.next_action_type or "").strip()
    if not next_action_type:
        if upi_qr_image_url or upi_qr_data:
            next_action_type = "upi_handle_redirect_or_display_qr_code"
        elif upi_redirect_url:
            next_action_type = "redirect_to_url"
    return UpiApiResponse(
        ok=True,
        reason="ok",
        retryable=None,
        message="",
        next_action_type=next_action_type,
        upi_redirect_url=upi_redirect_url,
        upi_qr_data=upi_qr_data,
        upi_qr_image_url=upi_qr_image_url,
        upi_hosted_url=str(result.upi_hosted_url or result.long_url or upi_redirect_url or upi_qr_image_url or upi_qr_data),
        request_id=request_id,
        duration_ms=duration_ms,
    )


def validate_upi_api_request(req: UpiApiRequest) -> None:
    token = normalize_access_token(req.token)
    if not token:
        raise HTTPException(status_code=400, detail="empty-token")
    if not looks_like_jwt(token):
        raise HTTPException(status_code=400, detail="invalid-token-format")
    if token_is_jwt_expired(token):
        raise HTTPException(status_code=400, detail="jwt-expired")
    if not UPI_FEATURE_ENABLED:
        raise HTTPException(status_code=403, detail="feature-disabled")
    if UPI_PHONE_ONLY:
        reg_type, _ = classify_registration_type(token)
        if reg_type != "phone":
            raise HTTPException(status_code=403, detail="account-not-phone")


async def run_upi_api(request: Request, req: UpiApiRequest) -> UpiApiResponse:
    require_upi_service_token(request)
    validate_upi_api_request(req)
    started_at = time.time()
    job_id = progress_job_id(f"upiapi-{uuid.uuid4().hex}")
    long_link_req = upi_request_to_long_link(req, job_id)
    result = generate_long_link_core(long_link_req)
    duration_ms = int((time.time() - started_at) * 1000)
    return upi_response_from_long_link(result, request_id=job_id, duration_ms=duration_ms)


def run_upi_api_internal(req: UpiApiRequest) -> UpiApiResponse:
    validate_upi_api_request(req)
    started_at = time.time()
    job_id = progress_job_id(f"upiapi-{uuid.uuid4().hex}")
    long_link_req = upi_request_to_long_link(req, job_id)
    result = generate_long_link_core(long_link_req)
    duration_ms = int((time.time() - started_at) * 1000)
    return upi_response_from_long_link(result, request_id=job_id, duration_ms=duration_ms)


def build_upi_streaming_response(req: UpiApiRequest) -> StreamingResponse:
    validate_upi_api_request(req)
    request_id = progress_job_id(f"upiapi-{uuid.uuid4().hex}")
    long_link_req = upi_request_to_long_link(req, request_id)

    async def event_stream():
        pool_keep = int(getattr(long_link_req, "pool_keep", UPI_DEFAULT_POOL_KEEP) or UPI_DEFAULT_POOL_KEEP)
        pool_max = int(getattr(long_link_req, "pool_max", UPI_DEFAULT_POOL_MAX) or UPI_DEFAULT_POOL_MAX)
        yield f"event: hello\ndata: {json.dumps({'request_id': request_id, 'pool_keep': pool_keep, 'pool_max': pool_max, 'queue_length': 0, 'inflight': 1, 'capacity': pool_keep}, ensure_ascii=False)}\n\n"
        task = asyncio.create_task(asyncio.to_thread(generate_long_link_core, long_link_req))
        last_ping = time.time()
        seen_progress = set()
        while not task.done():
            snapshot = get_progress(request_id)
            text = str(snapshot.get("text") or "")
            percent = int(snapshot.get("percent") or 0)
            done = bool(snapshot.get("done"))
            error = bool(snapshot.get("error"))
            marker = (text, percent, done, error)
            if text and marker not in seen_progress:
                seen_progress.add(marker)
                yield f"event: progress\ndata: {json.dumps({'type': 'step', 'step': text, 'percent': percent, 'done': done, 'error': error}, ensure_ascii=False)}\n\n"
            now = time.time()
            if now - last_ping >= UPI_SSE_PING_SECONDS:
                yield ": ping\n\n"
                last_ping = now
            await asyncio.sleep(0.5)
        try:
            result = await task
            response = upi_response_from_long_link(result, request_id=request_id, duration_ms=0)
            yield f"event: done\ndata: {response.model_dump_json(ensure_ascii=False)}\n\n"
        except Exception as exc:
            response = upi_error_response_from_exception(exc)
            payload = json.loads(response.body.decode("utf-8"))
            yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app = FastAPI(title="OpenAI Pay Long Link")
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.middleware("http")
async def disable_html_response_cache(request: Request, call_next: Any) -> Response:
    response = await call_next(request)
    content_type = str(response.headers.get("content-type") or "").lower()
    if content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.on_event("startup")
def start_pix_monitor() -> None:
    global _pix_monitor
    if _pix_monitor is not None:
        return
    _pix_monitor = PixMonitor(
        PixMonitorConfig(
            poll_interval_seconds=PIX_STATUS_POLL_INTERVAL_SECONDS,
            terminal_display_seconds=PIX_TERMINAL_DISPLAY_SECONDS,
            batch_limit=PIX_QUEUE_LIMIT,
            worker_count=PIX_MONITOR_WORKER_COUNT,
        ),
        PixMonitorDeps(
            list_items=list_pix_pending_sessions,
            save_item=save_pix_pending_session,
            poll_item=poll_pix_session_item,
            log_event=log_event,
            now=current_timestamp,
        ),
    )
    _pix_monitor.start()


@app.on_event("shutdown")
def stop_pix_monitor() -> None:
    global _pix_monitor
    if _pix_monitor is None:
        return
    _pix_monitor.stop()
    _pix_monitor = None


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error in openai-pay-long-link", exc_info=exc)
    bump_stats(error=str(exc) or exc.__class__.__name__)
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
        job_id = progress_job_id((payload or {}).get("job_id", ""))
        if job_id:
            set_progress(
                job_id,
                percent=100,
                text=progress_error_text(exc),
                done=True,
                error=True,
            )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "detail": str(exc) or exc.__class__.__name__,
            "error_type": exc.__class__.__name__,
        },
    )


@app.get("/login")
def login_page(request: Request, scope: str = ADMIN_SCOPE) -> Response:
    identity = request_identity(request, ZC_DEFAULT_JWT_SECRET)
    requested_scope = QR_SCOPE if str(scope or "").strip().lower() == QR_SCOPE else ADMIN_SCOPE
    granted_scope = str(identity.get("scope") or "")
    if not identity.get("auth_enabled"):
        next_path = normalize_next_path(request.query_params.get("next", ""), requested_scope)
        return RedirectResponse(url=next_path, status_code=303)
    if granted_scope == ADMIN_SCOPE or granted_scope == requested_scope:
        next_path = normalize_next_path(request.query_params.get("next", ""), requested_scope)
        return RedirectResponse(url=next_path, status_code=303)
    return FileResponse(LOGIN_PAGE)


@app.get("/")
def index(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
    return Response(html, media_type="text/html; charset=utf-8")


@app.get("/qr")
def qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(PUBLIC_DIR / "qr.html")


@app.get("/kr-qr")
def kr_qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(KR_QR_PAGE)


@app.get("/ch-qr")
def ch_qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(CH_QR_PAGE)


@app.get("/in-qr")
def in_qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(IN_QR_PAGE)


@app.get("/nl-qr")
def nl_qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(NL_QR_PAGE)


@app.get("/id-qr")
def id_qr_page(request: Request) -> Response:
    redirect = require_page_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(ID_QR_PAGE)


@app.get("/debug-generate")
def debug_generate_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(DEBUG_GENERATE_PAGE)


@app.get("/upi")
def upi_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(UPI_PAGE)


@app.get("/upi/tasks")
def upi_tasks_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(UPI_TASKS_PAGE)


@app.get("/upi/logs")
def upi_logs_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(UPI_LOGS_PAGE)


@app.get("/upi/result")
def upi_result_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(UPI_RESULT_PAGE)


@app.get("/favicon.svg")
def favicon_page() -> Response:
    return FileResponse(PUBLIC_DIR / "favicon.svg")


@app.get("/stats")
def stats_page(request: Request) -> Response:
    redirect = require_page_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    if redirect is not None:
        return redirect
    return FileResponse(STATS_PAGE)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        **request_identity(request, ZC_DEFAULT_JWT_SECRET),
    }


@app.post("/api/auth/login")
def auth_login(req: AuthLoginRequest) -> Response:
    scope = authenticate_scope(req.password, req.scope, ZC_DEFAULT_JWT_SECRET)
    next_path = normalize_next_path(req.next, scope)
    log_event("auth.login", "login succeeded", scope=scope)
    response = JSONResponse(
        {
            "ok": True,
            "scope": scope,
            "next": next_path,
        }
    )
    issue_auth_cookie(response, scope, ZC_DEFAULT_JWT_SECRET)
    return response


@app.post("/api/auth/logout")
def auth_logout() -> Response:
    log_event("auth.logout", "logout succeeded")
    response = JSONResponse({"ok": True})
    clear_auth_cookie(response)
    return response


@app.get("/api/stats")
def stats(request: Request) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return app_stats_snapshot()


@app.get("/api/logs")
def logs(request: Request, limit: int = 100) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return {
        "ok": True,
        "items": list_log_events(RUNTIME_DIR, limit=limit),
    }


@app.get("/api/checkout-progress")
def checkout_progress(request: Request, job_id: str = "") -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return get_progress(progress_job_id(job_id))


@app.get("/api/checkout-progress-many")
def checkout_progress_many(request: Request, job_ids: str = "") -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    raw_items = [item.strip() for item in str(job_ids or "").split(",")]
    return {
        "ok": True,
        "items": get_progress_many(raw_items),
    }


@app.get("/api/tasks")
def list_task_snapshots(request: Request, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    payload = list_progress_jobs_page(page=page, page_size=page_size)
    return {
        "ok": True,
        **payload,
    }


@app.get("/api/tasks/logs")
def task_logs(request: Request, job_id: str = "", limit: int = 200) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized_job_id = progress_job_id(job_id)
    if not normalized_job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    return {
        "ok": True,
        "job_id": normalized_job_id,
        "task": get_progress(normalized_job_id),
        "items": list_task_log_events(normalized_job_id, limit=limit),
    }


@app.get("/api/v1/upi/tasks")
def upi_task_list(request: Request, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    payload = list_progress_jobs_page(page=page, page_size=page_size)
    items = [item for item in payload.get("items", []) if isinstance(item.get("result"), dict) and str((item.get("result") or {}).get("link_type") or "").strip() == "upi"]
    summary = {
        "total": len(items),
        "running": len([item for item in items if not item.get("done")]),
        "done": len([item for item in items if item.get("done") and not item.get("error")]),
        "failed": len([item for item in items if item.get("error")]),
    }
    return {"ok": True, "items": items, "summary": summary, "page": 1, "page_size": len(items), "total": len(items), "total_pages": 1}


@app.get("/api/v1/upi/tasks/logs")
def upi_task_logs(request: Request, job_id: str = "", limit: int = 200) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized_job_id = progress_job_id(job_id)
    if not normalized_job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    task = get_progress(normalized_job_id)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if str((result or {}).get("link_type") or "").strip() != "upi":
        raise HTTPException(status_code=404, detail="upi task not found")
    return {"ok": True, "job_id": normalized_job_id, "task": task, "items": list_task_log_events(normalized_job_id, limit=limit)}


@app.get("/api/v1/upi/queue")
def upi_queue_items(request: Request, limit: int = 200) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return {"ok": True, "items": list_provider_pending_sessions("upi", limit=limit)}


@app.get("/api/upi/tasks")
def internal_upi_task_list(request: Request, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return upi_task_list(request, page=page, page_size=page_size)


@app.get("/api/upi/tasks/logs")
def internal_upi_task_logs(request: Request, job_id: str = "", limit: int = 200) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return upi_task_logs(request, job_id=job_id, limit=limit)


@app.get("/api/upi/queue")
def internal_upi_queue_items(request: Request, limit: int = 200) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return upi_queue_items(request, limit=limit)


@app.post("/api/tasks/delete")
def delete_task_snapshot(request: Request, req: TaskDeleteRequest) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    removed = delete_progress_job(req.job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="task not found")
    log_event("task.delete", "task snapshot deleted", job_id=req.job_id)
    return {"ok": True}


@app.post("/api/zc/accounts")
def zc_accounts(request: Request, req: ZCAccountsRequest) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    items = zc_fetch_accounts(req)
    return {
        "ok": True,
        "items": items,
        "total": len(items),
    }


@app.post("/api/zc/claim")
def zc_claim(request: Request, req: ZCClaimRequest) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    account = zc_claim_account(req)
    return {"ok": True, "account": account}


@app.post("/api/zc/release")
def zc_release(request: Request, req: ZCReleaseRequest) -> dict[str, Any]:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    data = zc_release_account(req)
    return {"ok": True, "data": data}


@app.post("/api/pix/status")
def pix_status(request: Request, req: PixStatusRequest) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return poll_pix_payment_status(req)


@app.get("/api/pix/pending")
def pix_pending(request: Request, limit: int = 20) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return {
        "ok": True,
        "items": list_pix_pending_sessions(limit=limit),
    }


@app.post("/api/pix/delete")
def pix_delete(request: Request, cs_id: str = "") -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        raise HTTPException(status_code=400, detail="cs_id is required")
    existing = get_pix_pending_session(normalized_cs_id)
    if not existing:
        raise HTTPException(status_code=404, detail="pix session not found")
    remove_pix_pending_session(normalized_cs_id)
    log_event("pix.delete", "pix session deleted", cs_id=normalized_cs_id, status=str(existing.get("state") or ""))
    return {"ok": True}


@app.post("/api/pix/clear-terminal")
def pix_clear_terminal(request: Request) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    removed = clear_terminal_pix_pending_sessions(RUNTIME_DIR)
    log_event("pix.clear_terminal", "terminal pix sessions cleared", status=str(removed))
    return {"ok": True, "removed": removed}


@app.get("/api/provider/pending")
def provider_pending(request: Request, link_type: str = "", limit: int = 20) -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized = normalize_link_type(link_type)
    if normalized not in {"korea", "swiss", "ideal", "upi"}:
        raise HTTPException(status_code=400, detail="provider link_type must be korea, swiss, ideal, or upi")
    return {
        "ok": True,
        "items": list_provider_pending_sessions(normalized, limit=limit),
    }


@app.post("/api/v1/upi", response_model=UpiApiResponse)
async def api_v1_upi(request: Request, req: UpiApiRequest) -> UpiApiResponse:
    return await run_upi_api(request, req)


@app.post("/api/v1/upi/stream")
async def api_v1_upi_stream(request: Request, req: UpiApiRequest) -> StreamingResponse:
    require_upi_service_token(request)
    return build_upi_streaming_response(req)


@app.post("/api/upi", response_model=UpiApiResponse)
async def internal_upi_api(request: Request, req: UpiApiRequest) -> UpiApiResponse:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return run_upi_api_internal(req)


@app.post("/api/upi/stream")
async def internal_upi_stream(request: Request, req: UpiApiRequest) -> StreamingResponse:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return build_upi_streaming_response(req)


@app.post("/api/provider/delete")
def provider_delete(request: Request, link_type: str = "", cs_id: str = "") -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized = normalize_link_type(link_type)
    if normalized not in {"korea", "swiss", "ideal", "upi"}:
        raise HTTPException(status_code=400, detail="provider link_type must be korea, swiss, ideal, or upi")
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        raise HTTPException(status_code=400, detail="cs_id is required")
    existing = get_provider_pending_session(normalized, normalized_cs_id)
    if not existing:
        raise HTTPException(status_code=404, detail="provider session not found")
    remove_provider_pending_session(normalized, normalized_cs_id)
    log_event("provider.delete", "provider session deleted", cs_id=normalized_cs_id, status=normalized)
    return {"ok": True}


@app.post("/api/provider/clear-terminal")
def provider_clear_terminal(request: Request, link_type: str = "") -> dict[str, Any]:
    require_api_scope(request, QR_SCOPE, ZC_DEFAULT_JWT_SECRET)
    normalized = normalize_link_type(link_type)
    if normalized not in {"korea", "swiss", "ideal", "upi"}:
        raise HTTPException(status_code=400, detail="provider link_type must be korea, swiss, ideal, or upi")
    removed = clear_terminal_provider_pending_sessions(RUNTIME_DIR, normalized)
    log_event("provider.clear_terminal", "terminal provider sessions cleared", status=f"{normalized}:{removed}")
    return {"ok": True, "removed": removed}


def is_pix_rebuildable_error(exc: Exception) -> bool:
    text = progress_error_text(exc).lower()
    markers = (
        "pix amount policy failed",
        "pix line is unavailable",
        "payment_method_types_mismatch",
        "checkout_confirm_error",
        "pix qr resolution timeout",
    )
    return any(marker in text for marker in markers)


def run_pix_provider_attempt(
    req: LongLinkRequest,
    claimed_account: dict[str, Any] | None,
    job_id: str,
    attempt: int,
) -> tuple[dict[str, Any], str, dict[str, Any], str, str]:
    set_progress(job_id, percent=24, text="创建 OpenAI Checkout", done=False, error=False)
    checkout, chatgpt = create_checkout_with_proxy_retry(req)
    checkout_short_url = str(checkout.get("checkout_url") or "").strip()
    if not checkout_short_url:
        raise HTTPException(status_code=502, detail="checkout response missing short link")
    provider_proxy = provider_stage_proxy(req)
    if provider_proxy:
        apply_provider_proxy(chatgpt, provider_proxy)
    if str(checkout.get("publishable_key") or "").strip():
        req.stripe_publishable_key = str(checkout.get("publishable_key") or "").strip()
    set_progress(job_id, percent=52, text="初始化 Stripe", done=False, error=False)
    init_payload = stripe_init(checkout["cs_id"], req, proxy_override=provider_proxy)
    bootstrap_methods = ",".join(checkout_payment_method_tokens(init_payload)) or "none"
    log_event(
        "pix.bootstrap_init",
        f"BR bootstrap Stripe init amount={expected_amount_int(init_payload)} methods={bootstrap_methods}",
        job_id=job_id,
        status="ok",
        cs_id=checkout["cs_id"],
    )
    ensure_pix_is_offered(init_payload, "bootstrap stripe init")
    set_progress(job_id, percent=64, text="VN 应用优惠和税区", done=False, error=False)
    sync_pix_promotion_and_br_taxes(chatgpt, checkout, req, provider_proxy, claimed_account, job_id)
    apply_provider_proxy(chatgpt, provider_proxy)
    set_progress(job_id, percent=70, text="BR final Stripe init", done=False, error=False)
    init_payload = pix_final_init_checked(checkout, req, provider_proxy, job_id)
    set_progress(job_id, percent=78, text=provider_generation_progress_text("pix"), done=False, error=False)
    provider_fields = create_provider_link(
        chatgpt,
        checkout,
        init_payload,
        "",
        req,
        provider_proxy=provider_proxy,
        job_id=job_id,
    )
    return checkout, checkout_short_url, provider_fields, payment_method_type_for_link_type("pix"), ""


def run_pix_provider_with_rebuild(
    req: LongLinkRequest,
    claimed_account: dict[str, Any] | None,
    job_id: str,
) -> tuple[dict[str, Any], str, dict[str, Any], str, str]:
    attempts = max(1, int(PIX_REBUILD_ATTEMPTS or 1))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            set_progress(job_id, percent=24, text=f"Rebuild PIX checkout {attempt}/{attempts}", done=False, error=False)
            log_event("pix.rebuild", f"attempt {attempt}/{attempts} rebuilding checkout", job_id=job_id, status="pending")
        try:
            return run_pix_provider_attempt(req, claimed_account, job_id, attempt)
        except Exception as exc:
            if not is_pix_rebuildable_error(exc) or attempt >= attempts:
                raise
            last_error = exc
            log_event(
                "pix.rebuild",
                f"attempt {attempt}/{attempts} failed, rebuilding: {progress_error_text(exc)}",
                job_id=job_id,
                status="pending",
            )
    raise last_error or HTTPException(status_code=502, detail="pix rebuild failed")


def generate_long_link_core(req: LongLinkRequest) -> LongLinkResponse:
    bump_stats(request=True)
    job_id = progress_job_id(req.job_id)
    log_event("task.start", "generation started", job_id=job_id, status=normalize_link_type(req.link_type))
    resolved_zc_base_url = effective_zc_base_url(req.zc_base_url)
    resolved_zc_token = effective_zc_token(req.zc_token)
    resolved_zc_password = effective_zc_password(req.zc_password)
    claimed_account: dict[str, Any] | None = None
    set_progress(job_id, percent=5, text="读取 Token", done=False, error=False)
    link_type = normalize_link_type(req.link_type)
    try:
        claimed_account = maybe_claim_zc_account(req, job_id)
        if link_type == "pix":
            checkout, checkout_short_url, provider_fields, payment_method_type, stripe_hosted_url = run_pix_provider_with_rebuild(
                req,
                claimed_account,
                job_id,
            )
        else:
            set_progress(job_id, percent=24, text="创建 OpenAI Checkout", done=False, error=False)
            checkout, chatgpt = create_checkout_with_proxy_retry(req)
            checkout_short_url = str(checkout.get("checkout_url") or "").strip()
            if not checkout_short_url:
                raise HTTPException(status_code=502, detail="checkout response missing short link")

            provider_fields: dict[str, Any] = {
                "payment_method_id": "",
                "stripe_redirect_url": "",
                "provider_redirect_url": "",
                "long_url": checkout_short_url,
                "pix_hosted_instructions_url": "",
                "pix_qr_code": "",
                "pix_qr_image_url_png": "",
                "pix_qr_image_url_svg": "",
                "pix_expires_at": 0,
            }
            payment_method_type = ""
            stripe_hosted_url = ""
            if link_type in {"korea", "swiss", "ideal", "upi", "gopay", "gcash", "grabpay"}:
                provider_proxy = provider_stage_proxy(req)
                if provider_proxy:
                    apply_provider_proxy(chatgpt, provider_proxy)
                if str(checkout.get("publishable_key") or "").strip():
                    req.stripe_publishable_key = str(checkout.get("publishable_key") or "").strip()
                set_progress(job_id, percent=52, text="初始化 Stripe", done=False, error=False)
                init_payload = stripe_init(checkout["cs_id"], req, proxy_override=provider_proxy)
                provider_text = provider_generation_progress_text(link_type)
                set_progress(job_id, percent=78, text=provider_text, done=False, error=False)
                provider_fields = create_provider_link(
                    chatgpt,
                    checkout,
                    init_payload,
                    stripe_hosted_url,
                    req,
                    provider_proxy=provider_proxy,
                    job_id=job_id,
                )
                if link_type == "korea":
                    provider_fields = enrich_korea_provider_fields(provider_fields, req, provider_proxy=provider_proxy)
                payment_method_type = payment_method_type_for_link_type(link_type)

        set_progress(job_id, percent=96, text="整理结果", done=False, error=False)
        result = LongLinkResponse(
            ok=True,
            cs_id=checkout["cs_id"],
            processor_entity=checkout["processor_entity"],
            checkout_url=checkout_short_url,
            billing_country=checkout["billing_country"],
            currency=checkout["currency"],
            payment_locale=locale_parts(effective_payment_locale(req.link_type, req.payment_locale))[0],
            link_type=link_type,
            payment_method_type=payment_method_type,
            payment_method_id=str(provider_fields.get("payment_method_id") or ""),
            stripe_redirect_url=str(provider_fields.get("stripe_redirect_url") or ""),
            provider_redirect_url=str(provider_fields.get("provider_redirect_url") or ""),
            fallback=False,
            provider_error="",
            stripe_hosted_url=stripe_hosted_url,
            long_url=str(provider_fields.get("long_url") or "").strip() or checkout_short_url,
            provider_qr_url=str(provider_fields.get("provider_qr_url") or ""),
            provider_qr_svg=str(provider_fields.get("provider_qr_svg") or ""),
            provider_expires_at=int(provider_fields.get("provider_expires_at") or 0),
            provider_ios_app_url=str(provider_fields.get("provider_ios_app_url") or ""),
            provider_aos_app_url=str(provider_fields.get("provider_aos_app_url") or ""),
            pix_hosted_instructions_url=str(provider_fields.get("pix_hosted_instructions_url") or ""),
            pix_qr_code=str(provider_fields.get("pix_qr_code") or ""),
            pix_qr_image_url_png=str(provider_fields.get("pix_qr_image_url_png") or ""),
            pix_qr_image_url_svg=str(provider_fields.get("pix_qr_image_url_svg") or ""),
            pix_expires_at=int(provider_fields.get("pix_expires_at") or 0),
            approval_result=str(provider_fields.get("approval_result") or ""),
            submission_state=str(provider_fields.get("submission_state") or ""),
            completion_stage=str(provider_fields.get("completion_stage") or ""),
            claimed_account_email=str(claimed_account.get("email") or "").strip() if claimed_account else "",
            claimed_account_id=int(claimed_account.get("id") or 0) if claimed_account else 0,
            claimed_via_zc=bool(claimed_account),
            claimed_claim_key=str(claimed_account.get("claim_key") or "").strip() if claimed_account else "",
            claimed_claim_expires_at=str(claimed_account.get("claim_expires_at") or "").strip() if claimed_account else "",
        )
        bump_stats(success=True, fallback=False)
        log_event(
            "task.done",
            "generation completed",
            job_id=job_id,
            cs_id=checkout["cs_id"],
            status="ok",
        )
        provider_display_ready = bool(
            str(provider_fields.get("provider_redirect_url") or "").strip()
            or str(provider_fields.get("long_url") or "").strip()
            or str(provider_fields.get("upi_hosted_url") or "").strip()
            or str(provider_fields.get("pix_hosted_instructions_url") or "").strip()
        )
        if link_type in {"korea", "swiss", "ideal", "upi", "pix"} and provider_display_ready:
            save_provider_pending_session(
                {
                    "csId": checkout["cs_id"],
                    "linkType": link_type,
                    "state": "pending",
                    "paymentMethodType": payment_method_type,
                    "paymentMethodId": str(provider_fields.get("payment_method_id") or ""),
                    "checkoutUrl": checkout_short_url,
                    "longUrl": str(provider_fields.get("long_url") or "").strip(),
                    "providerRedirectUrl": str(provider_fields.get("provider_redirect_url") or "").strip(),
                    "stripeRedirectUrl": str(provider_fields.get("stripe_redirect_url") or "").strip(),
                    "paymentPageUrl": str(
                        provider_fields.get("provider_redirect_url")
                        or provider_fields.get("long_url")
                        or provider_fields.get("upi_hosted_url")
                        or provider_fields.get("pix_hosted_instructions_url")
                        or provider_fields.get("stripe_redirect_url")
                        or ""
                    ).strip(),
                    "queuePagePath": provider_page_path_for_link_type(link_type),
                    "qrUrl": str(provider_fields.get("provider_qr_url") or "").strip(),
                    "qrSvg": str(provider_fields.get("provider_qr_svg") or ""),
                    "expiredAt": int(provider_fields.get("provider_expires_at") or 0),
                    "iosAppUrl": str(provider_fields.get("provider_ios_app_url") or "").strip(),
                    "aosAppUrl": str(provider_fields.get("provider_aos_app_url") or "").strip(),
                    "bridgeUrl": str(provider_fields.get("provider_bridge_url") or "").strip(),
                    "providerStatus": str(provider_fields.get("provider_status") or "").strip(),
                    "kakaoTid": str(provider_fields.get("provider_kakao_tid") or "").strip(),
                }
            )
        set_progress(
            job_id,
            percent=100,
            text="生成完成",
            done=True,
            error=False,
            result=result.model_dump(),
        )
        return result
    except Exception as exc:
        log_event("task.failed", "generation failed", job_id=job_id, status=exc.__class__.__name__)
        set_progress(
            job_id,
            percent=100,
            text=progress_error_text(exc),
            done=True,
            error=True,
        )
        if claimed_account and zc_account_has_claim(claimed_account):
            fatal_error_code = detect_fatal_account_error(exc)
            try:
                if fatal_error_code in FATAL_ACCOUNT_ERROR_CODES and int(claimed_account.get("id") or 0) > 0:
                    zc_delete_account(
                        base_url=resolved_zc_base_url,
                        token=resolved_zc_token,
                        password=resolved_zc_password,
                        account_id=int(claimed_account.get("id") or 0),
                    )
                    log_event(
                        "task.account_deleted",
                        "claimed account deleted from ZC after fatal auth error",
                        job_id=job_id,
                        status=fatal_error_code,
                        cs_id=str(claimed_account.get("id") or ""),
                    )
                else:
                    zc_release_account(
                        ZCReleaseRequest(
                            baseUrl=resolved_zc_base_url,
                            token=resolved_zc_token,
                            password=resolved_zc_password,
                            claimKey=str(claimed_account.get("claim_key") or req.zc_claim_key or progress_job_id(req.job_id)),
                            accountId=int(claimed_account.get("id") or 0) or None,
                        )
                    )
            except Exception:
                pass
        raise


@app.post("/api/long-link", response_model=LongLinkResponse)
def generate_long_link(request: Request, req: LongLinkRequest) -> LongLinkResponse:
    require_api_scope(request, ADMIN_SCOPE, ZC_DEFAULT_JWT_SECRET)
    return generate_long_link_core(req)


@app.post("/api/debug/long-link", response_model=LongLinkResponse)
def generate_debug_long_link(request: Request, req: LongLinkRequest) -> LongLinkResponse:
    return generate_long_link(request, req)


from paylink.compat_facade import register_compatibility_routes


compatibility_facade = register_compatibility_routes(
    app,
    request_factory=LongLinkRequest,
    generate_core=generate_long_link_core,
    set_progress=set_progress,
    get_progress=get_progress,
    log_event=log_event,
)
