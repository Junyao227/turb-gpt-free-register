#!/usr/bin/env python3
"""Delete every Roxy profile, then create and open one profile per proxy."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:50100"
DEFAULT_LIST_PATH = "/browser/list"
DEFAULT_CREATE_PATH = "/browser/create"
DEFAULT_OPEN_PATH = "/browser/open"
DEFAULT_CLOSE_PATH = "/browser/close"
DEFAULT_DELETE_PATH = "/browser/delete"
SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
DEFAULT_CONFIG_FILE = Path(__file__).with_suffix(".txt")


class RoxyApiError(RuntimeError):
    """Raised when Roxy returns a failed or unusable API response."""


@dataclass(frozen=True)
class ProxySpec:
    raw: str
    protocol: str
    host: str
    port: int
    username: str
    password: str

    @property
    def masked(self) -> str:
        auth = "***:***@" if self.username or self.password else ""
        return f"{self.protocol.lower()}://{auth}{self.host}:{self.port}"

    def roxy_proxy_info(self, check_channel: str) -> dict[str, Any]:
        category = {
            "http": "HTTP",
            "https": "HTTPS",
            "socks5": "SOCKS5",
            "socks5h": "SOCKS5",
        }[self.protocol]
        data: dict[str, Any] = {
            "moduleId": 0,
            "proxyMethod": "custom",
            "proxyCategory": category,
            "ipType": "IPV4",
            "protocol": category,
            "host": self.host,
            "port": str(self.port),
        }
        if self.username:
            data["proxyUserName"] = self.username
        if self.password:
            data["proxyPassword"] = self.password
        if check_channel:
            data["checkChannel"] = check_channel
        return data


def redact(text: object, secrets: Iterable[str]) -> str:
    result = str(text or "")
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    return result


def parse_proxy(line: str) -> ProxySpec:
    raw = str(line or "").strip()
    if not raw:
        raise ValueError("proxy is empty")
    candidate = raw if "://" in raw else f"http://{raw}"

    # Support the common host:port:user:password form without losing colons in passwords.
    if "@" not in candidate and "://" in candidate:
        scheme, remainder = candidate.split("://", 1)
        parts = remainder.split(":", 3)
        if len(parts) == 4:
            host, port, username, password = parts
            candidate = f"{scheme}://{username}:{password}@{host}:{port}"

    parsed = urlparse(candidate)
    protocol = parsed.scheme.lower()
    if protocol not in SUPPORTED_PROXY_SCHEMES:
        raise ValueError(f"unsupported proxy scheme: {protocol or '-'}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("proxy port is invalid") from exc
    if not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise ValueError("proxy must include host and port")
    return ProxySpec(
        raw=raw,
        protocol=protocol,
        host=parsed.hostname,
        port=port,
        username=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
    )


def load_proxies(path: Path) -> list[ProxySpec]:
    if not path.is_file():
        raise FileNotFoundError(f"proxy file does not exist: {path}")
    proxies: list[ProxySpec] = []
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        try:
            proxies.append(parse_proxy(value))
        except ValueError as exc:
            errors.append(f"line {line_number}: {exc}")
    if errors:
        raise ValueError("invalid proxy file:\n" + "\n".join(errors))
    if not proxies:
        raise ValueError("proxy file contains no usable proxy")
    return proxies


def load_config(path: Path) -> dict[str, str]:
    """Load a simple KEY=VALUE text file without external dependencies."""
    if not path.is_file():
        raise FileNotFoundError(f"config file does not exist: {path}")
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#") or text.startswith(";"):
            continue
        if "=" not in text:
            raise ValueError(f"config line {line_number} must use KEY=VALUE")
        key, value = text.split("=", 1)
        key = key.strip().upper()
        if not key:
            raise ValueError(f"config line {line_number} has an empty key")
        values[key] = value.strip()
    return values


def config_value(config: dict[str, str], key: str, default: str) -> str:
    file_value = config.get(key, "").strip()
    if file_value:
        return file_value
    return os.getenv(key, default)


def config_bool(config: dict[str, str], key: str, default: bool) -> bool:
    value = config_value(config, key, "true" if default else "false").lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be true or false")


class RoxyClient:
    def __init__(self, api_base: str, token: str, timeout: int):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self.api_base + "/" + path.lstrip("/")
        if params:
            url += "?" + urlencode(params)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["token"] = self.token
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RoxyApiError(f"{method.upper()} {path} returned HTTP {exc.code}: {raw[:500]}") from exc
        except URLError as exc:
            raise RoxyApiError(f"{method.upper()} {path} could not connect: {exc.reason}") from exc

        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RoxyApiError(f"{method.upper()} {path} returned non-JSON data") from exc
        if not isinstance(data, dict):
            return {"data": data}
        code = data.get("code")
        explicit_success = data.get("ok") is True or data.get("success") is True
        if code not in (None, 0, 200, "0", "200") and not explicit_success:
            message = data.get("msg") or data.get("message") or data.get("error") or raw[:500]
            raise RoxyApiError(f"{method.upper()} {path} failed: {message}")
        return data


def nested_value(payload: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                break
            current = current.get(key)
        else:
            if current is not None:
                return current
    return None


def extract_profile_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = nested_value(
        payload,
        ("data", "rows"),
        ("data", "list"),
        ("data", "records"),
        ("data", "items"),
        ("data",),
        ("rows",),
        ("list",),
        ("records",),
        ("items",),
    )
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def profile_id(item: dict[str, Any]) -> str:
    for key in ("dirId", "dir_id", "profileId", "profile_id", "browserId", "browser_id", "id"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def coerce_id(value: str) -> str | int:
    return int(value) if value.isdigit() else value


def list_all_profiles(
    client: RoxyClient,
    path: str,
    method: str,
    workspace_id: str,
    page_size: int,
) -> list[str]:
    profiles: list[str] = []
    seen: set[str] = set()
    for page in range(1, 1001):
        body = {
            "workspaceId": coerce_id(workspace_id),
            "page": page,
            "pageNum": page,
            "pageNo": page,
            "pageSize": page_size,
            "size": page_size,
        }
        payload = client.request(
            method,
            path,
            body if method.upper() != "GET" else None,
            body if method.upper() == "GET" else None,
        )
        items = extract_profile_items(payload)
        for item in items:
            item_id = profile_id(item)
            if item_id and item_id not in seen:
                seen.add(item_id)
                profiles.append(item_id)
        if len(items) < page_size:
            break
    else:
        raise RoxyApiError("profile pagination exceeded 1000 pages")
    return profiles


def close_and_delete_all(
    client: RoxyClient,
    profile_ids: list[str],
    workspace_id: str,
    close_path: str,
    delete_path: str,
    close_wait: float,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for index, item_id in enumerate(profile_ids, start=1):
        payload = {"workspaceId": coerce_id(workspace_id), "dirId": coerce_id(item_id)}
        try:
            client.request("POST", close_path, payload)
        except Exception as exc:
            failures.append({"profile_id": item_id, "stage": "close", "error": redact(exc, [client.token])})
        if close_wait:
            time.sleep(close_wait)
        try:
            client.request(
                "POST",
                delete_path,
                {"workspaceId": coerce_id(workspace_id), "dirIds": [coerce_id(item_id)]},
            )
            print(f"[{index}/{len(profile_ids)}] deleted profile {item_id}")
        except Exception as exc:
            failures.append({"profile_id": item_id, "stage": "delete", "error": redact(exc, [client.token])})
    return failures


def create_profiles(
    client: RoxyClient,
    proxies: list[ProxySpec],
    workspace_id: str,
    project_id: str,
    create_path: str,
    open_path: str,
    os_name: str,
    check_channel: str,
    open_windows: bool,
    name_prefix: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    created: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for index, proxy in enumerate(proxies, start=1):
        payload: dict[str, Any] = {
            "workspaceId": coerce_id(workspace_id),
            "projectId": coerce_id(project_id),
            "name": f"{name_prefix}-{index:04d}",
            "os": os_name,
            "proxyInfo": proxy.roxy_proxy_info(check_channel),
        }
        try:
            response = client.request("POST", create_path, payload)
            item_id = str(
                nested_value(
                    response,
                    ("dirId",),
                    ("dir_id",),
                    ("id",),
                    ("profileId",),
                    ("profile_id",),
                    ("data", "dirId"),
                    ("data", "dir_id"),
                    ("data", "id"),
                    ("data", "profileId"),
                    ("data", "profile_id"),
                )
                or ""
            ).strip()
            if not item_id:
                raise RoxyApiError("create response did not include a profile ID")
            created.append({"profile_id": item_id, "proxy": proxy.masked})
            print(f"[{index}/{len(proxies)}] created profile {item_id} for {proxy.masked}")
        except Exception as exc:
            failures.append({"proxy": proxy.masked, "stage": "create", "error": redact(exc, [proxy.raw, client.token])})
            continue

        if not open_windows:
            continue
        try:
            client.request(
                "POST",
                open_path,
                {
                    "workspaceId": coerce_id(workspace_id),
                    "dirId": coerce_id(item_id),
                    "args": [],
                    "forceOpen": True,
                    "headless": False,
                },
            )
            print(f"[{index}/{len(proxies)}] opened profile {item_id}")
        except Exception as exc:
            failures.append({"profile_id": item_id, "proxy": proxy.masked, "stage": "open", "error": redact(exc, [proxy.raw, client.token])})
    return created, failures


def parse_args() -> tuple[argparse.Namespace, Path]:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_FILE)
    bootstrap_args, _ = bootstrap.parse_known_args()
    config_path = bootstrap_args.config.expanduser().resolve()
    config = load_config(config_path)

    parser = argparse.ArgumentParser(
        description="Delete every Roxy profile, then create and open one profile per proxy.",
        parents=[bootstrap],
    )
    parser.add_argument("--proxy-file", type=Path, default=config_value(config, "PROXY_FILE", "proxies.txt"), help="UTF-8 file with one proxy per line")
    parser.add_argument("--api-base", default=config_value(config, "ROXY_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--token", default=config_value(config, "ROXY_API_TOKEN", ""), help="Defaults to ROXY_API_TOKEN")
    parser.add_argument("--workspace-id", default=config_value(config, "ROXY_WORKSPACE_ID", ""))
    parser.add_argument("--project-id", default=config_value(config, "ROXY_PROJECT_ID", ""))
    parser.add_argument("--list-path", default=config_value(config, "ROXY_LIST_PATH", DEFAULT_LIST_PATH))
    parser.add_argument("--list-method", default=config_value(config, "ROXY_LIST_METHOD", "POST").upper(), choices=("GET", "POST"))
    parser.add_argument("--create-path", default=config_value(config, "ROXY_CREATE_PATH", DEFAULT_CREATE_PATH))
    parser.add_argument("--open-path", default=config_value(config, "ROXY_OPEN_PATH", DEFAULT_OPEN_PATH))
    parser.add_argument("--close-path", default=config_value(config, "ROXY_CLOSE_PATH", DEFAULT_CLOSE_PATH))
    parser.add_argument("--delete-path", default=config_value(config, "ROXY_DELETE_PATH", DEFAULT_DELETE_PATH))
    parser.add_argument("--os", dest="os_name", default=config_value(config, "ROXY_DEFAULT_OS", "macOS"))
    parser.add_argument("--check-channel", default=config_value(config, "ROXY_PROXY_CHECK_CHANNEL", ""))
    parser.add_argument("--name-prefix", default=config_value(config, "ROXY_NAME_PREFIX", "bulk-proxy"))
    parser.add_argument("--page-size", type=int, default=int(config_value(config, "ROXY_PAGE_SIZE", "100")))
    parser.add_argument("--close-wait", type=float, default=float(config_value(config, "ROXY_CLOSE_WAIT", "1")))
    parser.add_argument("--timeout", type=int, default=int(config_value(config, "ROXY_TIMEOUT", "30")))
    parser.add_argument("--no-open", dest="open_windows", action="store_false", default=config_bool(config, "ROXY_OPEN_WINDOWS", True), help="Create profiles without opening browser windows")
    parser.add_argument("--open", dest="open_windows", action="store_true", help="Create profiles and open browser windows")
    parser.add_argument("--dry-run", action="store_true", help="List current profiles and validate proxies without changing Roxy")
    parser.add_argument("--yes", action="store_true", help="Skip the destructive-operation confirmation prompt")
    return parser.parse_args(), config_path


def main() -> int:
    args, config_path = parse_args()
    if args.page_size < 1 or args.timeout < 1 or args.close_wait < 0:
        raise ValueError("page size and timeout must be positive; close wait cannot be negative")
    if not args.workspace_id or not args.project_id:
        raise ValueError("ROXY_WORKSPACE_ID and ROXY_PROJECT_ID must be set in the config file or command line")
    proxy_path = args.proxy_file.expanduser()
    if not proxy_path.is_absolute():
        proxy_path = config_path.parent / proxy_path
    proxies = load_proxies(proxy_path)
    client = RoxyClient(args.api_base, args.token, args.timeout)
    profile_ids = list_all_profiles(client, args.list_path, args.list_method, args.workspace_id, args.page_size)

    print(f"Roxy profiles to delete: {len(profile_ids)}")
    print(f"Proxies to create: {len(proxies)}")
    if args.dry_run:
        print("Dry run complete. No Roxy profile was deleted or created.")
        return 0

    if not args.yes:
        confirmation = input("Type DELETE to remove every listed Roxy profile: ").strip()
        if confirmation != "DELETE":
            print("Cancelled. No Roxy profile was changed.")
            return 2

    delete_failures = close_and_delete_all(
        client,
        profile_ids,
        args.workspace_id,
        args.close_path,
        args.delete_path,
        args.close_wait,
    )
    created, create_failures = create_profiles(
        client,
        proxies,
        args.workspace_id,
        args.project_id,
        args.create_path,
        args.open_path,
        args.os_name,
        args.check_channel,
        args.open_windows,
        args.name_prefix,
    )
    summary = {
        "deleted_requested": len(profile_ids),
        "created": created,
        "failures": delete_failures + create_failures,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RoxyApiError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
