"""CDK 管理端集成客户端。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests


class CdkManagementError(RuntimeError):
    """CDK 管理端请求或响应不符合预期。"""


def _management_origin() -> str:
    from config import codex as config

    raw = str(getattr(config, "CDK_MGMT_MANAGEMENT_URL", "") or "").strip()
    if not raw:
        raise CdkManagementError("尚未配置 CDK_MGMT_MANAGEMENT_URL")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CdkManagementError("CDK_MGMT_MANAGEMENT_URL 格式无效")
    return f"{parsed.scheme}://{parsed.netloc}"


def _management_key() -> str:
    from config import codex as config

    key = str(getattr(config, "CDK_MGMT_MANAGEMENT_KEY", "") or "").strip()
    if not key:
        raise CdkManagementError("尚未配置 CDK_MGMT_MANAGEMENT_KEY")
    return key


def _request_timeout() -> int:
    from config import codex as config

    return max(1, int(getattr(config, "CDK_MGMT_REQUEST_TIMEOUT", 30) or 30))


def _response_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "detail", "reason"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
    return fallback


def import_cpa_file(*, email: str, content: str | bytes, filename: str, source_filename: str = "") -> dict[str, Any]:
    """把 CPA 原始 JSON 交给 CDK 管理端创建或补全对应记录。"""
    normalized_email = str(email or "").strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise CdkManagementError("本地 Codex 记录缺少有效邮箱")

    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    if not data:
        raise CdkManagementError("CPA 文件为空")

    key = _management_key()
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
        "X-Management-Key": key,
        "User-Agent": "turb-gpt-free-register/cdk-management",
    }
    try:
        response = requests.post(
            f"{_management_origin()}/api/management/import-cpa",
            headers=headers,
            data={
                "email": normalized_email,
                "source": "gpt-registrator",
                "source_filename": str(source_filename or "").strip(),
            },
            files={"file": (str(filename or "cpa.json"), data, "application/json")},
            timeout=_request_timeout(),
        )
    except requests.RequestException as exc:
        raise CdkManagementError(f"CDK 管理端连接失败：{exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        raise CdkManagementError(
            f"CDK 管理端接口失败 status={response.status_code}: "
            f"{_response_message(payload, '未返回可识别错误信息')}"
        )
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise CdkManagementError(_response_message(payload, "CDK 管理端返回无效响应"))
    return payload
