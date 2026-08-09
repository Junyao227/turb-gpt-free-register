from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

TERMINAL_STATES = frozenset({"succeeded", "failed", "expired", "canceled"})


@dataclass(frozen=True)
class PixMonitorConfig:
    poll_interval_seconds: int
    terminal_display_seconds: int
    batch_limit: int
    worker_count: int


@dataclass(frozen=True)
class PixMonitorDeps:
    list_items: Callable[[int], list[dict[str, Any]]]
    save_item: Callable[[dict[str, Any]], None]
    poll_item: Callable[[dict[str, Any]], dict[str, Any]]
    log_event: Callable[..., None]
    now: Callable[[], int]


class PixMonitor:
    def __init__(self, config: PixMonitorConfig, deps: PixMonitorDeps) -> None:
        self._config = config
        self._deps = deps
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="pix-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._process_batch()
            self._stop_event.wait(self._config.poll_interval_seconds)

    def _process_batch(self) -> None:
        items = self._deps.list_items(self._config.batch_limit)
        if not items:
            return
        cursor = {"value": 0}
        cursor_lock = threading.Lock()

        def worker() -> None:
            while True:
                with cursor_lock:
                    index = cursor["value"]
                    cursor["value"] += 1
                if index >= len(items):
                    return
                self._process_item(items[index])

        worker_total = max(1, min(self._config.worker_count, len(items)))
        threads = [
            threading.Thread(target=worker, name=f"pix-monitor-worker-{index + 1}", daemon=True)
            for index in range(worker_total)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def _process_item(self, item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        if self._state_of(item) in TERMINAL_STATES:
            return
        now_ts = self._deps.now()
        try:
            result = self._deps.poll_item(item)
        except Exception:
            if self._mark_expired_if_needed(item, now_ts):
                return
            self._deps.save_item(
                {
                    **item,
                    "nextCheckAt": now_ts + self._config.poll_interval_seconds,
                }
            )
            return
        if self._state_of(result) in TERMINAL_STATES:
            return
        if self._mark_expired_if_needed(item, now_ts):
            return
        self._deps.save_item(
            {
                **item,
                "nextCheckAt": now_ts + self._config.poll_interval_seconds,
            }
        )

    def _mark_expired_if_needed(self, item: dict[str, Any], now_ts: int) -> bool:
        expires_at = int(item.get("pixExpiresAt") or 0)
        if not expires_at or expires_at > now_ts:
            return False
        finished_at = now_ts
        self._deps.save_item(
            {
                **item,
                "state": "expired",
                "paymentObjectStatus": "expired",
                "finishedAt": finished_at,
                "nextCheckAt": 0,
                "removeAfter": finished_at + self._config.terminal_display_seconds,
            }
        )
        self._deps.log_event(
            "pix.expired",
            "pix session expired by monitor",
            cs_id=str(item.get("csId") or ""),
            status="expired",
        )
        return True

    def _state_of(self, item: dict[str, Any] | None) -> str:
        return str((item or {}).get("state") or "pending").strip().lower() or "pending"
