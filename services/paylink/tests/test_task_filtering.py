from pathlib import Path
import sys

from fastapi import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
        }
    )


def test_task_snapshots_filter_by_provider_and_keep_failed_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(app, "_progress_jobs", {})
    monkeypatch.setattr(app, "require_api_scope", lambda *_args, **_kwargs: None)

    app.set_progress("pix-job", percent=100, text="done", done=True, link_type="pix")
    app.set_progress("upi-failed", percent=100, text="failed", done=True, error=True, link_type="upi")
    app.set_progress(
        "legacy-kakao",
        percent=100,
        text="done",
        done=True,
        result={"_compatibility_facade": True, "value": {"payment_link_type": "kakao_pay"}},
    )
    app.set_progress("gcash-job", percent=100, text="done", done=True, link_type="gcash")
    app.set_progress("paypal-job", percent=100, text="done", done=True, link_type="paypal")

    upi = app.list_task_snapshots(request_for("/api/tasks"), provider="upi")
    kakao = app.list_task_snapshots(request_for("/api/tasks"), provider="kakao_pay")
    pix = app.list_task_snapshots(request_for("/api/tasks"), provider="pix")
    gcash = app.list_task_snapshots(request_for("/api/tasks"), provider="gcash")
    paypal = app.list_task_snapshots(request_for("/api/tasks"), provider="paypal")

    assert [item["job_id"] for item in upi["items"]] == ["upi-failed"]
    assert upi["summary"] == {"total": 1, "running": 0, "done": 0, "failed": 1}
    assert [item["job_id"] for item in kakao["items"]] == ["legacy-kakao"]
    assert kakao["items"][0]["link_type"] == "korea"
    assert [item["job_id"] for item in pix["items"]] == ["pix-job"]
    assert [item["job_id"] for item in gcash["items"]] == ["gcash-job"]
    assert [item["job_id"] for item in paypal["items"]] == ["paypal-job"]
