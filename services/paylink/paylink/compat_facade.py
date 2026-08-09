from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .provider_config import ProviderConfigError
from .provider_registry import ResolvedProvider, enabled_provider_metadata, resolve_provider
from .redact import redact_text


class ExtractRequest(BaseModel):
    token: str = ""
    link_type: str = "pix"


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _model_data(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        data = value.model_dump()
    elif isinstance(value, dict):
        data = dict(value)
    else:
        data = {}
    return data if isinstance(data, dict) else {}


def normalize_result(raw_result: Any, public_type: str) -> dict[str, Any]:
    result = _model_data(raw_result)
    long_url = next(
        (
            str(result.get(field) or "").strip()
            for field in ("long_url", "provider_redirect_url", "upi_hosted_url", "pix_hosted_instructions_url", "checkout_url")
            if str(result.get(field) or "").strip()
        ),
        "",
    )
    copy_paste = next(
        (
            str(result.get(field) or "").strip()
            for field in ("provider_qr_url", "upi_qr_data", "pix_qr_code")
            if str(result.get(field) or "").strip()
        ),
        "",
    )
    image_url_png = next(
        (
            str(result.get(field) or "").strip()
            for field in ("pix_qr_image_url_png", "upi_qr_image_url")
            if str(result.get(field) or "").strip()
        ),
        "",
    )
    image_url_svg = next(
        (
            str(result.get(field) or "")
            for field in ("pix_qr_image_url_svg", "provider_qr_svg")
            if str(result.get(field) or "").strip()
        ),
        "",
    )
    expires_at = int(result.get("provider_expires_at") or result.get("pix_expires_at") or 0)
    return {
        "long_url": long_url,
        "copy_paste": copy_paste,
        "image_url_png": image_url_png,
        "image_url_svg": image_url_svg,
        "payment_method": str(result.get("payment_method_type") or "").strip(),
        "payment_link_type": public_type,
        "expires_at": expires_at,
    }


class CompatibilityFacade:
    def __init__(
        self,
        *,
        request_factory: Callable[..., Any],
        generate_core: Callable[[Any], Any],
        set_progress: Callable[..., None],
        get_progress: Callable[[str], dict[str, Any]],
        log_event: Callable[..., None],
        provider_resolver: Callable[[str], ResolvedProvider] = resolve_provider,
    ) -> None:
        self._request_factory = request_factory
        self._generate_core = generate_core
        self._set_progress = set_progress
        self._get_progress = get_progress
        self._log_event = log_event
        self._provider_resolver = provider_resolver
        self._running_jobs: set[str] = set()
        self._lock = threading.Lock()

    def create_job(self, request: ExtractRequest) -> str:
        provider = self._provider_resolver(request.link_type)
        job_id = uuid.uuid4().hex
        self._set_progress(
            job_id,
            percent=1,
            text="Paylink job created",
            done=False,
            error=False,
            link_type=provider.definition.native_type,
        )
        with self._lock:
            self._running_jobs.add(job_id)
        worker = threading.Thread(
            target=self._run_job,
            args=(job_id, str(request.token or ""), provider),
            name=f"paylink-{provider.definition.public_type}-{job_id[:8]}",
            daemon=True,
        )
        worker.start()
        return job_id

    def _run_job(self, job_id: str, token: str, provider: ResolvedProvider) -> None:
        try:
            if not token.strip():
                raise ValueError("access token is required")
            self._log_event(
                "facade.start",
                f"{provider.definition.display_name} generation started",
                job_id=job_id,
                status="running",
            )
            generation_request = self._request_factory(
                accessToken=token,
                link_type=provider.definition.native_type,
                billing_country=provider.settings.country,
                payment_locale=provider.settings.locale,
                job_id=job_id,
            )
            raw_result = self._generate_core(generation_request)
            result = normalize_result(raw_result, provider.definition.public_type)
            self._set_progress(
                job_id,
                percent=100,
                text="Paylink generation completed",
                done=True,
                error=False,
                result={"_compatibility_facade": True, "value": result},
            )
            self._log_event("facade.done", "paylink generation completed", job_id=job_id, status="ok")
        except Exception as exc:
            message = redact_text(str(exc) or exc.__class__.__name__)
            self._set_progress(job_id, percent=100, text=message, done=True, error=True)
            self._log_event("facade.failed", message, job_id=job_id, status="failed")
        finally:
            with self._lock:
                self._running_jobs.discard(job_id)

    def _is_running(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._running_jobs

    def iter_events(self, job_id: str) -> Iterator[str]:
        last_state: tuple[Any, ...] | None = None
        last_heartbeat = time.monotonic()
        while True:
            snapshot = self._get_progress(job_id)
            if not snapshot.get("ok"):
                yield _sse("error", {"error": "paylink job not found"})
                yield _sse("done", {"ok": False})
                return

            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            is_compatibility_result = bool(result.get("_compatibility_facade"))
            if bool(snapshot.get("done")) and not is_compatibility_result and not bool(snapshot.get("error")):
                if self._is_running(job_id):
                    time.sleep(0.1)
                    continue
                self._set_progress(
                    job_id,
                    percent=100,
                    text="paylink job interrupted before facade result was saved",
                    done=True,
                    error=True,
                )
                continue
            if not bool(snapshot.get("done")) and not self._is_running(job_id):
                self._set_progress(
                    job_id,
                    percent=100,
                    text="paylink job interrupted by service restart",
                    done=True,
                    error=True,
                )
                continue

            state = (
                snapshot.get("percent"),
                snapshot.get("text"),
                snapshot.get("done"),
                snapshot.get("error"),
                snapshot.get("updated_at"),
            )
            if state != last_state and not bool(snapshot.get("done")):
                last_state = state
                yield _sse(
                    "log",
                    {
                        "message": redact_text(snapshot.get("text") or "Paylink job running"),
                        "percent": int(snapshot.get("percent") or 0),
                    },
                )
            if bool(snapshot.get("done")):
                if bool(snapshot.get("error")):
                    yield _sse("error", {"error": redact_text(snapshot.get("text") or "paylink job failed")})
                    yield _sse("done", {"ok": False})
                    return
                value = result.get("value") if is_compatibility_result else None
                if not isinstance(value, dict):
                    yield _sse("error", {"error": "paylink job returned an invalid result"})
                    yield _sse("done", {"ok": False})
                    return
                yield _sse("result", {"result": value})
                yield _sse("done", {"ok": True})
                return
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                last_heartbeat = now
                yield ": keep-alive\n\n"
            time.sleep(0.2)


def register_compatibility_routes(
    app: Any,
    *,
    request_factory: Callable[..., Any],
    generate_core: Callable[[Any], Any],
    set_progress: Callable[..., None],
    get_progress: Callable[[str], dict[str, Any]],
    log_event: Callable[..., None],
) -> CompatibilityFacade:
    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=generate_core,
        set_progress=set_progress,
        get_progress=get_progress,
        log_event=log_event,
    )
    router = APIRouter()

    @router.post("/api/extract")
    def create_extract(request: ExtractRequest) -> JSONResponse:
        try:
            job_id = facade.create_job(request)
        except ProviderConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"ok": True, "job_id": job_id}, status_code=202)

    @router.get("/api/providers")
    def get_providers() -> JSONResponse:
        try:
            providers = enabled_provider_metadata()
        except ProviderConfigError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse({"ok": True, "providers": list(providers)})

    @router.get("/api/jobs/{job_id}/events")
    def extract_events(job_id: str) -> StreamingResponse:
        return StreamingResponse(
            facade.iter_events(str(job_id or "").strip()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.include_router(router)
    return facade
