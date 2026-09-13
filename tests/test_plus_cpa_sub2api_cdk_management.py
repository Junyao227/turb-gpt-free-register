from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1] / "kuozhan" / "plus-cpa-sub2api-cdk-management"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import db, settings


def build_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data", raising=False)
    monkeypatch.setattr(settings, "RECORDS_DIR", tmp_path / "data" / "records", raising=False)
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "data" / "cdk_mgmt.sqlite3", raising=False)
    monkeypatch.setattr(settings, "SESSION_SECRET", "test-session-secret", raising=False)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin-password", raising=False)
    settings.ensure_dirs()
    db.init_db()
    import app.main as main

    importlib.reload(main)
    return TestClient(main.app)


def create_ready_record(client: TestClient) -> dict[str, str]:
    login = client.post("/api/admin/login", json={"password": "test-admin-password"})
    assert login.status_code == 200
    assert login.json()["ok"] is True

    created = client.post("/api/admin/records", json={"buyer_email": "mark@example.com", "notes": "demo"})
    assert created.status_code == 200
    record = created.json()["record"]
    record_id = record["id"]

    cpa = client.post(
        f"/api/admin/records/{record_id}/upload-cpa",
        files={"file": ("cpa.json", b"CPA-1", "application/json")},
    )
    assert cpa.status_code == 200

    sub2api = client.post(
        f"/api/admin/records/{record_id}/upload-sub2api",
        files={"file": ("sub2api.json", b"SUB2API-2", "application/json")},
    )
    assert sub2api.status_code == 200

    record = client.get(f"/api/admin/records/{record_id}").json()["record"]
    assert record["status"] == "available"
    return record


def test_buyer_lookup_accepts_cdk_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = build_client(monkeypatch, tmp_path)
    record = create_ready_record(client)

    resp = client.post("/api/buyer/lookup", json={"redeem_string": f"cdk: {record['redeem_code']}----{record['buyer_email']}"})
    assert resp.status_code == 200
    payload = resp.json()["record"]
    assert payload["id"] == record["id"]
    assert payload["ready"] is True
    assert payload["redeemed"] is False


def test_buyer_redeem_once_then_reopen_and_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = build_client(monkeypatch, tmp_path)
    record = create_ready_record(client)
    redeem_string = f"{record['redeem_code']}----{record['buyer_email']}"

    first = client.post("/api/buyer/redeem", json={"redeem_string": redeem_string})
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["record"]["already_redeemed"] is False
    assert first_payload["record"]["redeemed"] is True
    assert first_payload["record"]["download_urls"]["cpa"].startswith("/api/buyer/download/")

    second = client.post("/api/buyer/redeem", json={"redeem_string": f"cdk: {redeem_string}"})
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["record"]["already_redeemed"] is True
    assert second_payload["record"]["download_urls"]["sub2api"].startswith("/api/buyer/download/")

    cpa_resp = client.get(second_payload["record"]["download_urls"]["cpa"])
    assert cpa_resp.status_code == 200
    assert cpa_resp.content == b"CPA-1"

    sub2api_resp = client.get(second_payload["record"]["download_urls"]["sub2api"])
    assert sub2api_resp.status_code == 200
    assert sub2api_resp.content == b"SUB2API-2"


def test_admin_events_show_chinese_summaries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = build_client(monkeypatch, tmp_path)
    record = create_ready_record(client)

    events = client.get("/api/admin/events?limit=10")
    assert events.status_code == 200
    rows = events.json()["events"]

    assert rows[0]["record_buyer_email"] == "mark@example.com"
    assert rows[0]["record_redeem_code"] == record["redeem_code"]
    assert "文件已上传" in rows[0]["detail"] or "兑换字符串" in rows[0]["detail"]
    assert any("记录已创建" in row["detail"] for row in rows)
    assert any("兑换字符串" in row["detail"] and "邮箱 mark@example.com" in row["detail"] for row in rows)


def test_admin_auth_required_for_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = build_client(monkeypatch, tmp_path)

    forbidden = client.get("/api/admin/records")
    assert forbidden.status_code == 401

    bad_login = client.post("/api/admin/login", json={"password": "wrong"})
    assert bad_login.status_code == 401
    assert bad_login.json()["detail"] == "密码错误"


def test_management_import_creates_once_and_validates_cpa_email(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "MANAGEMENT_KEY", "test-management-key", raising=False)
    client = build_client(monkeypatch, tmp_path)
    payload = {
        "type": "codex",
        "access_token": "access-token-1",
        "session_token": "session-token-1",
        "email": "mark@example.com",
    }

    unauthorized = client.post(
        "/api/management/import-cpa",
        data={"email": "mark@example.com"},
        files={"file": ("mark.json", json.dumps(payload), "application/json")},
    )
    assert unauthorized.status_code == 401

    headers = {"X-Management-Key": "test-management-key"}
    created = client.post(
        "/api/management/import-cpa",
        headers=headers,
        data={"email": "mark@example.com", "source": "gpt-registrator"},
        files={"file": ("mark.json", json.dumps(payload), "application/json")},
    )
    assert created.status_code == 200
    first = created.json()["result"]
    assert first["action"] == "created"
    assert first["has_cpa"] is True
    assert first["has_sub2api"] is False
    assert "redeem_code" not in first

    repeated = client.post(
        "/api/management/import-cpa",
        headers=headers,
        data={"email": "mark@example.com"},
        files={"file": ("mark.json", json.dumps(payload), "application/json")},
    )
    assert repeated.status_code == 200
    assert repeated.json()["result"]["action"] == "already_exists"
    assert repeated.json()["result"]["record_id"] == first["record_id"]

    mismatch = client.post(
        "/api/management/import-cpa",
        headers=headers,
        data={"email": "other@example.com"},
        files={"file": ("mark.json", json.dumps(payload), "application/json")},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"] == "CPA 文件邮箱与请求邮箱不一致"
