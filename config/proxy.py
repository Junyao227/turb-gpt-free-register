# -*- coding: utf-8 -*-
"""
代理池配置

每次注册随机抽取一个代理，保证不同 sid 之间彼此独立，避免风控关联。

协议说明：
    - http:// / https://   HTTP(S) 代理
    - socks5://            SOCKS5（DNS 本地解析，可能泄漏）
    - socks5h://           SOCKS5（DNS 在代理端解析，推荐，避免 DNS-IP 错配）
"""
import random
import re
from urllib.parse import quote, unquote, urlsplit

from config.env_loader import apply_env_overrides


# 本地代理入口；实际出口地区以代理/分流规则为准。
# 推荐使用 socks5h://（DNS 在代理端解析），避免本地 DNS 与出口 IP 地区错配。
PROXY_POOL = [
    "socks5://127.0.0.1:7897",
]

# 代理池使用的本地上游代理。填写后形成：本地上游 -> 代理池目标代理 -> ChatGPT；
# 留空则直接使用代理池中的目标代理，不启动链式中继。
PROXY_POOL_UPSTREAM_PROXY = ""

# 套餐/Plus 试用资格查询与 Codex Agent Token 生成共用这组独立网络策略，
# 避免批量请求被注册代理池中的临时本地代理拖垮，也避免无条件直连造成出口策略失控。
#   auto   = 优先使用 PLAN_CHECK_PROXY 或代理池；没有代理时才按 direct 运行
#   proxy  = 强制使用 PLAN_CHECK_PROXY 或代理池，失败直接报错
#   direct = 始终直连
PLAN_CHECK_PROXY_MODE = "auto"

# 套餐查询 / Codex Agent Token 生成专用代理。留空时 auto/proxy 模式从 PROXY_POOL 选择。
# 代理可能包含账号密码，因此 WebUI 会把它保存到 .env。
PLAN_CHECK_PROXY = []

# 套餐查询 / Codex Agent Token 生成的上游代理。填写后形成：本地代理 -> 动态代理 -> ChatGPT。
# 例如 http://127.0.0.1:7897；留空则直接连接 PLAN_CHECK_PROXY。
PLAN_CHECK_UPSTREAM_PROXY = ""

# 查套餐 / 生成 Codex Agent Token 使用独立的短超时和有限重试，避免后台任务长时间卡住。
PLAN_CHECK_TIMEOUT = 15.0
PLAN_CHECK_MAX_ATTEMPTS = 3
PLAN_CHECK_RETRY_DELAY = 2.0

# 新注册账号的权益可能存在短暂同步延迟。首次查询失败，或返回 free 且暂未发现
# Plus 试用资格时，等待该秒数后再复查一次；设为 0 可关闭复查。
PLAN_CHECK_REGISTRATION_RECHECK_DELAY = 2.0

# 自动、手动和批量套餐查询共用同一个后台队列；Codex Agent Token 使用独立队列，
# 但复用这里的网络模式、请求启动间隔与随机抖动，避免批量后台请求过于集中。
PLAN_CHECK_WORKERS = 3
PLAN_CHECK_QUEUE_LIMIT = 500
PLAN_CHECK_MIN_INTERVAL = 1.0
PLAN_CHECK_JITTER = 0.8


_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
_KNOWN_PROXY_PROVIDERS = (
    ("kookeey.info", "kookeey"),
    ("bunnyproxy.com", "bunnyproxy"),
    ("cliproxy.io", "cliproxy"),
    ("1024proxy.io", "1024proxy"),
    ("ipipbright.net", "ipipbright"),
)
_COUNTRY_CODE_RE = re.compile(r"^[a-z]{2}$", re.I)


def normalize_proxy_url(value: str, default_scheme: str = "http") -> str:
    """将常见代理写法统一成 scheme://user:pass@host:port。"""
    text = str(value or "").strip()
    if not text:
        return ""

    scheme = str(default_scheme or "http").strip().lower()
    remainder = text
    if "://" in text:
        scheme, remainder = text.split("://", 1)
        scheme = scheme.strip().lower()
    if scheme not in _PROXY_SCHEMES:
        raise ValueError(f"不支持的代理协议: {scheme or '-'}")

    # 标准认证 URL 直接交给 urlsplit；无认证 URL 还要兼容方括号 IPv6。
    legacy_parts = None
    parts = remainder.split(":", 3)
    if len(parts) == 4 and parts[1].isdigit() and 1 <= int(parts[1]) <= 65535:
        legacy_parts = tuple(parts)
    elif not remainder.startswith("[") and len(parts) == 4 and parts[3].isdigit() and 1 <= int(parts[3]) <= 65535:
        username, password, host, port = parts
        legacy_parts = (host, port, username, password)
    elif "@" not in remainder:
        if remainder.startswith("["):
            closing_bracket = remainder.find("]")
            if closing_bracket >= 0 and remainder[closing_bracket + 1:].startswith(":"):
                host = remainder[:closing_bracket + 1]
                suffix_parts = remainder[closing_bracket + 2:].split(":", 2)
                if len(suffix_parts) == 3:
                    legacy_parts = (host, *suffix_parts)
                elif len(suffix_parts) != 1:
                    raise ValueError("代理格式应为 user:password@host:port 或 host:port:user:password")
        else:
            parts = remainder.split(":", 3)
            if len(parts) == 4:
                legacy_parts = tuple(parts)
            elif len(parts) != 2:
                raise ValueError("代理格式应为 user:password@host:port 或 host:port:user:password")

    if legacy_parts is None:
        normalized = f"{scheme}://{remainder}"
    else:
        # 兼容 host:port:user:password；只切前三个冒号，密码中的冒号归入 password。
        host, port, username, password = (part.strip() for part in legacy_parts)
        if not host or not port or not username or not password:
            raise ValueError("代理 host、port、username、password 均不能为空")
        normalized = f"{scheme}://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"

    try:
        parsed = urlsplit(normalized)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        if "://" not in text and legacy_parts is None:
            return text
        raise ValueError("代理端口格式错误") from exc
    if not host or port is None:
        raise ValueError("代理格式缺少 host/port")
    if not 1 <= port <= 65535:
        raise ValueError("代理端口超出 1-65535")
    return normalized


def mask_proxy_url(value: str) -> str:
    """Return a display-safe proxy URL without username or password."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        normalized = normalize_proxy_url(text)
        parsed = urlsplit(normalized)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        auth = "***:***@" if parsed.username or parsed.password else ""
        return f"{parsed.scheme}://{auth}{host}{port}" or "***"
    except (TypeError, ValueError):
        return "***"


def _known_proxy_provider(host: str) -> tuple[str, str] | None:
    for domain, provider in _KNOWN_PROXY_PROVIDERS:
        if host == domain or host.endswith(f".{domain}"):
            return provider, domain
    return None


def _country_code_from_host(host: str, provider_domain: str) -> str:
    host_labels = host.split(".")
    domain_labels = provider_domain.split(".")
    prefix_labels = host_labels[:-len(domain_labels)]
    for label in reversed(prefix_labels):
        if _COUNTRY_CODE_RE.fullmatch(label):
            return label.lower()
    return ""


def _country_code_from_auth_value(value: str) -> str:
    match = re.search(r"(?:^|[-_])(?:country|region|area)[-_:]?([a-z]{2})(?=[-_]|$)", value, re.I)
    return match.group(1).lower() if match else ""


def proxy_display_label(value: str) -> str:
    """Return a concise provider/region label when the proxy format is known."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        normalized = normalize_proxy_url(text)
        parsed = urlsplit(normalized)
    except (TypeError, ValueError):
        return "***"

    host = str(parsed.hostname or "").lower()
    provider_info = _known_proxy_provider(host)
    if provider_info:
        provider, provider_domain = provider_info
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        country = (
            _country_code_from_auth_value(username)
            or _country_code_from_auth_value(password)
            or _country_code_from_host(host, provider_domain)
        )
        if provider == "kookeey" and not country:
            parts = re.split(r"[-_]", password)
            candidate = parts[1] if len(parts) > 1 else ""
            country = candidate.lower() if _COUNTRY_CODE_RE.fullmatch(candidate) else ""
        return f"{provider}-{country}" if country else provider

    return mask_proxy_url(normalized)


def normalize_proxy_list(values, default_scheme: str = "http") -> list[str]:
    """Normalize a multiline proxy list and omit empty entries."""
    if values is None:
        return []
    if isinstance(values, str):
        values = values.splitlines()
    return [
        normalized
        for value in values
        if (normalized := normalize_proxy_url(value, default_scheme=default_scheme))
    ]


def pick_proxy() -> str:
    """从代理池中随机抽取一个代理 URL；池为空时返回空串（即不使用代理）。"""
    return normalize_proxy_url(random.choice(PROXY_POOL)) if PROXY_POOL else ""


# 兼容入口：默认每次进程启动随机选一个，作为本次注册全程的固定代理
PROXY = pick_proxy()

# ---- .env overrides for WebUI editable fields ----
apply_env_overrides(globals(), {
    'PROXY_POOL': 'list_str_multiline',
    'PROXY_POOL_UPSTREAM_PROXY': 'str',
    'PLAN_CHECK_PROXY_MODE': 'str',
    'PLAN_CHECK_PROXY': 'list_str_multiline',
    'PLAN_CHECK_UPSTREAM_PROXY': 'str',
    'PLAN_CHECK_TIMEOUT': 'float',
    'PLAN_CHECK_MAX_ATTEMPTS': 'int',
    'PLAN_CHECK_RETRY_DELAY': 'float',
    'PLAN_CHECK_REGISTRATION_RECHECK_DELAY': 'float',
    'PLAN_CHECK_WORKERS': 'int',
    'PLAN_CHECK_QUEUE_LIMIT': 'int',
    'PLAN_CHECK_MIN_INTERVAL': 'float',
    'PLAN_CHECK_JITTER': 'float',
})
PROXY_POOL = normalize_proxy_list(PROXY_POOL)
PLAN_CHECK_PROXY = normalize_proxy_list(PLAN_CHECK_PROXY)
PROXY = pick_proxy()
