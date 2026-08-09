from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

PIX_PENDING_FILE_NAME = "pix_pending_sessions.json"
PROVIDER_PENDING_FILE_NAME = "provider_pending_sessions.json"
TASK_SNAPSHOTS_FILE_NAME = "task_snapshots.json"
LOG_EVENTS_FILE_NAME = "event_logs.jsonl"
TASK_RETENTION_SECONDS = 7 * 24 * 60 * 60
PIX_ACTIVE_RETENTION_SECONDS = 7 * 24 * 60 * 60
PIX_FINISHED_RETENTION_SECONDS = 24 * 60 * 60
LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60
MAX_TASK_SNAPSHOTS = 500
MAX_PIX_PENDING = 200
MAX_PROVIDER_PENDING = 200
MAX_LOG_EVENTS = 2000

_task_lock = threading.Lock()
_pix_lock = threading.Lock()
_provider_lock = threading.Lock()
_log_lock = threading.Lock()


def ensure_runtime_dir(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)


def _data_file(runtime_dir: Path, filename: str) -> Path:
    ensure_runtime_dir(runtime_dir)
    return runtime_dir / filename


def _read_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError(f"{path} must contain a JSON list")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise RuntimeError(f"{path} item {index} is not an object")
        items.append(dict(item))
    return items


def _write_items(path: Path, items: list[dict[str, Any]]) -> None:
    ensure_runtime_dir(path.parent)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_task_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    job_id = str(snapshot.get("job_id") or "").strip()
    if not job_id:
        raise RuntimeError("task snapshot missing job_id")
    now_ts = time.time()
    created_at = float(snapshot.get("created_at") or now_ts)
    updated_at = float(snapshot.get("updated_at") or now_ts)
    normalized = {
        "ok": True,
        "job_id": job_id,
        "percent": max(0, min(100, int(snapshot.get("percent") or 0))),
        "text": str(snapshot.get("text") or ""),
        "done": bool(snapshot.get("done")),
        "error": bool(snapshot.get("error")),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    link_type = str(snapshot.get("link_type") or "").strip().lower()
    if link_type:
        normalized["link_type"] = link_type
    result = snapshot.get("result")
    if isinstance(result, dict):
        normalized["result"] = result
    return normalized


def _prune_task_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = time.time() - TASK_RETENTION_SECONDS
    pruned: list[dict[str, Any]] = []
    for item in items:
        normalized = _normalize_task_snapshot(item)
        if normalized["updated_at"] < cutoff:
            continue
        pruned.append(normalized)
    pruned.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return pruned[:MAX_TASK_SNAPSHOTS]


def load_task_snapshot_map(runtime_dir: Path) -> dict[str, dict[str, Any]]:
    with _task_lock:
        path = _data_file(runtime_dir, TASK_SNAPSHOTS_FILE_NAME)
        items = _prune_task_items(_read_items(path))
        _write_items(path, items)
    return {str(item["job_id"]): item for item in items}


def prune_task_snapshot_map(snapshot_map: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    items = _prune_task_items(list(snapshot_map.values()))
    return {str(item["job_id"]): item for item in items}


def save_task_snapshot(runtime_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_task_snapshot(snapshot)
    with _task_lock:
        path = _data_file(runtime_dir, TASK_SNAPSHOTS_FILE_NAME)
        items = _prune_task_items(_read_items(path))
        item_map = {str(item["job_id"]): item for item in items}
        item_map[normalized["job_id"]] = normalized
        saved_items = _prune_task_items(list(item_map.values()))
        _write_items(path, saved_items)
    return normalized


def remove_task_snapshot(runtime_dir: Path, job_id: str) -> bool:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    with _task_lock:
        path = _data_file(runtime_dir, TASK_SNAPSHOTS_FILE_NAME)
        items = _prune_task_items(_read_items(path))
        filtered = [item for item in items if str(item.get("job_id") or "").strip() != normalized_job_id]
        if len(filtered) == len(items):
            return False
        _write_items(path, filtered)
    return True


def _normalize_pix_session(session_data: dict[str, Any]) -> dict[str, Any]:
    cs_id = str(session_data.get("csId") or session_data.get("cs_id") or "").strip()
    if not cs_id:
        raise RuntimeError("pix session missing csId")
    normalized = dict(session_data)
    normalized["csId"] = cs_id
    return normalized


def _prune_pix_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now_ts = int(time.time())
    pruned: list[dict[str, Any]] = []
    for item in items:
        normalized = _normalize_pix_session(item)
        finished_at = int(normalized.get("finishedAt") or 0)
        remove_after = int(normalized.get("removeAfter") or 0)
        created_at = int(normalized.get("createdAt") or normalized.get("updatedAt") or 0)
        if remove_after and now_ts >= remove_after:
            continue
        if finished_at and not remove_after and now_ts - finished_at > PIX_FINISHED_RETENTION_SECONDS:
            continue
        if not finished_at and created_at and now_ts - created_at > PIX_ACTIVE_RETENTION_SECONDS:
            continue
        pruned.append(normalized)
    pruned.sort(key=lambda item: int(item.get("createdAt") or item.get("updatedAt") or 0))
    return pruned[:MAX_PIX_PENDING]


def save_pix_pending_session(runtime_dir: Path, session_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(session_data, dict):
        raise TypeError("session_data must be a dict")
    now_ts = int(time.time())
    normalized = _normalize_pix_session(session_data)
    with _pix_lock:
        path = _data_file(runtime_dir, PIX_PENDING_FILE_NAME)
        items = _prune_pix_items(_read_items(path))
        item_map = {str(item["csId"]): item for item in items}
        existing = item_map.get(normalized["csId"], {})
        merged = {**existing, **normalized}
        merged["createdAt"] = int(existing.get("createdAt") or existing.get("updatedAt") or now_ts)
        merged["updatedAt"] = now_ts
        item_map[normalized["csId"]] = merged
        saved_items = _prune_pix_items(list(item_map.values()))
        _write_items(path, saved_items)
    return merged


def get_pix_pending_session(runtime_dir: Path, cs_id: str) -> dict[str, Any] | None:
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        return None
    with _pix_lock:
        path = _data_file(runtime_dir, PIX_PENDING_FILE_NAME)
        items = _prune_pix_items(_read_items(path))
        _write_items(path, items)
    for item in items:
        if str(item.get("csId") or "").strip() == normalized_cs_id:
            return dict(item)
    return None


def remove_pix_pending_session(runtime_dir: Path, cs_id: str) -> None:
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_cs_id:
        return
    with _pix_lock:
        path = _data_file(runtime_dir, PIX_PENDING_FILE_NAME)
        items = _prune_pix_items(_read_items(path))
        items = [item for item in items if str(item.get("csId") or "").strip() != normalized_cs_id]
        _write_items(path, items)


def clear_terminal_pix_pending_sessions(runtime_dir: Path) -> int:
    terminal_states = {"succeeded", "failed", "expired", "canceled"}
    with _pix_lock:
        path = _data_file(runtime_dir, PIX_PENDING_FILE_NAME)
        items = _prune_pix_items(_read_items(path))
        filtered = [
            item for item in items
            if str(item.get("state") or "").strip().lower() not in terminal_states
        ]
        removed = len(items) - len(filtered)
        if removed:
            _write_items(path, filtered)
    return removed


def list_pix_pending_sessions(runtime_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    with _pix_lock:
        path = _data_file(runtime_dir, PIX_PENDING_FILE_NAME)
        items = _prune_pix_items(_read_items(path))
        _write_items(path, items)
    bounded_limit = max(1, min(int(limit or 20), MAX_PIX_PENDING))
    return items[:bounded_limit]


def _normalize_provider_session(session_data: dict[str, Any]) -> dict[str, Any]:
    cs_id = str(session_data.get("csId") or session_data.get("cs_id") or "").strip()
    if not cs_id:
        raise RuntimeError("provider session missing csId")
    link_type = str(session_data.get("linkType") or session_data.get("link_type") or "").strip().lower()
    if not link_type:
        raise RuntimeError("provider session missing linkType")
    normalized = dict(session_data)
    normalized["csId"] = cs_id
    normalized["linkType"] = link_type
    return normalized


def _prune_provider_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now_ts = int(time.time())
    pruned: list[dict[str, Any]] = []
    for item in items:
        normalized = _normalize_provider_session(item)
        finished_at = int(normalized.get("finishedAt") or 0)
        remove_after = int(normalized.get("removeAfter") or 0)
        created_at = int(normalized.get("createdAt") or normalized.get("updatedAt") or 0)
        if remove_after and now_ts >= remove_after:
            continue
        if finished_at and not remove_after and now_ts - finished_at > PIX_FINISHED_RETENTION_SECONDS:
            continue
        if not finished_at and created_at and now_ts - created_at > PIX_ACTIVE_RETENTION_SECONDS:
            continue
        pruned.append(normalized)
    pruned.sort(key=lambda item: int(item.get("createdAt") or item.get("updatedAt") or 0))
    return pruned[:MAX_PROVIDER_PENDING]


def save_provider_pending_session(runtime_dir: Path, session_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(session_data, dict):
        raise TypeError("session_data must be a dict")
    now_ts = int(time.time())
    normalized = _normalize_provider_session(session_data)
    with _provider_lock:
        path = _data_file(runtime_dir, PROVIDER_PENDING_FILE_NAME)
        items = _prune_provider_items(_read_items(path))
        item_map = {
            f"{str(item['linkType'])}:{str(item['csId'])}": item
            for item in items
        }
        key = f"{normalized['linkType']}:{normalized['csId']}"
        existing = item_map.get(key, {})
        merged = {**existing, **normalized}
        merged["createdAt"] = int(existing.get("createdAt") or existing.get("updatedAt") or now_ts)
        merged["updatedAt"] = now_ts
        item_map[key] = merged
        saved_items = _prune_provider_items(list(item_map.values()))
        _write_items(path, saved_items)
    return merged


def list_provider_pending_sessions(runtime_dir: Path, link_type: str, limit: int = 20) -> list[dict[str, Any]]:
    normalized_link_type = str(link_type or "").strip().lower()
    if not normalized_link_type:
        return []
    with _provider_lock:
        path = _data_file(runtime_dir, PROVIDER_PENDING_FILE_NAME)
        items = _prune_provider_items(_read_items(path))
        _write_items(path, items)
    filtered = [item for item in items if str(item.get("linkType") or "").strip().lower() == normalized_link_type]
    bounded_limit = max(1, min(int(limit or 20), MAX_PROVIDER_PENDING))
    return filtered[:bounded_limit]


def get_provider_pending_session(runtime_dir: Path, link_type: str, cs_id: str) -> dict[str, Any] | None:
    normalized_link_type = str(link_type or "").strip().lower()
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_link_type or not normalized_cs_id:
        return None
    items = list_provider_pending_sessions(runtime_dir, normalized_link_type, limit=MAX_PROVIDER_PENDING)
    for item in items:
        if str(item.get("csId") or "").strip() == normalized_cs_id:
            return dict(item)
    return None


def remove_provider_pending_session(runtime_dir: Path, link_type: str, cs_id: str) -> bool:
    normalized_link_type = str(link_type or "").strip().lower()
    normalized_cs_id = str(cs_id or "").strip()
    if not normalized_link_type or not normalized_cs_id:
        return False
    with _provider_lock:
        path = _data_file(runtime_dir, PROVIDER_PENDING_FILE_NAME)
        items = _prune_provider_items(_read_items(path))
        filtered = [
            item
            for item in items
            if not (
                str(item.get("linkType") or "").strip().lower() == normalized_link_type
                and str(item.get("csId") or "").strip() == normalized_cs_id
            )
        ]
        if len(filtered) == len(items):
            return False
        _write_items(path, filtered)
    return True


def clear_terminal_provider_pending_sessions(runtime_dir: Path, link_type: str) -> int:
    normalized_link_type = str(link_type or "").strip().lower()
    if not normalized_link_type:
        return 0
    terminal_states = {"succeeded", "failed", "expired", "canceled"}
    with _provider_lock:
        path = _data_file(runtime_dir, PROVIDER_PENDING_FILE_NAME)
        items = _prune_provider_items(_read_items(path))
        filtered = [
            item
            for item in items
            if not (
                str(item.get("linkType") or "").strip().lower() == normalized_link_type
                and str(item.get("state") or "").strip().lower() in terminal_states
            )
        ]
        removed = len(items) - len(filtered)
        if removed:
            _write_items(path, filtered)
    return removed


def _normalize_log_event(event: dict[str, Any]) -> dict[str, Any]:
    ts = int(event.get("ts") or time.time())
    kind = str(event.get("kind") or "").strip()
    if not kind:
        raise RuntimeError("log event missing kind")
    message = str(event.get("message") or "").strip()
    if not message:
        raise RuntimeError("log event missing message")
    normalized = {
        "ts": ts,
        "kind": kind,
        "message": message,
    }
    for key in ("job_id", "cs_id", "status", "scope"):
        value = str(event.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _read_log_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        raw = line.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path} line {index + 1} is not an object")
        items.append(_normalize_log_event(payload))
    return items


def _write_log_events(path: Path, items: list[dict[str, Any]]) -> None:
    ensure_runtime_dir(path.parent)
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _prune_log_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = int(time.time()) - LOG_RETENTION_SECONDS
    pruned = [item for item in items if int(item.get("ts") or 0) >= cutoff]
    pruned.sort(key=lambda item: int(item.get("ts") or 0), reverse=True)
    return pruned[:MAX_LOG_EVENTS]


def append_log_event(runtime_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_log_event(event)
    with _log_lock:
        path = _data_file(runtime_dir, LOG_EVENTS_FILE_NAME)
        items = _prune_log_events(_read_log_events(path))
        items.insert(0, normalized)
        items = _prune_log_events(items)
        _write_log_events(path, items)
    return normalized


def list_log_events(runtime_dir: Path, limit: int = 50) -> list[dict[str, Any]]:
    with _log_lock:
        path = _data_file(runtime_dir, LOG_EVENTS_FILE_NAME)
        items = _prune_log_events(_read_log_events(path))
        _write_log_events(path, items)
    bounded_limit = max(1, min(int(limit or 50), MAX_LOG_EVENTS))
    return items[:bounded_limit]
