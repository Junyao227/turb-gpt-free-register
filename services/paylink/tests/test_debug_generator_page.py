import asyncio
import json
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app

PUBLIC_DIR = Path(app.PUBLIC_DIR)


def read_public_asset(relative_path: str) -> str:
    return (PUBLIC_DIR / relative_path).read_text(encoding="utf-8")


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


def test_debug_generate_asset_exists():
    path = Path(app.DEBUG_GENERATE_PAGE)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "/api/debug/long-link" in text
    assert "autoClaimZc: false" in text
    assert "Provider 线路调试" in text
    assert "印度 UPI（IN / INR）" in text
    assert "菲律宾 GCash（PH / PHP）" in text
    assert "美国 PayPal（US / USD）" in text
    assert "印尼 GoPay（ID / IDR）" in text
    assert "Twint（CH / CHF）" in text
    assert "菲律宾 GCash（PH / PHP）" in text
    assert "菲律宾 GrabPay（PH / PHP）" in text
    assert "upi_hosted_url" in text
    assert "pix_hosted_instructions_url" in text
    assert "approvalResult" in text
    assert "submissionState" in text
    assert "function resultIsDisplaySuccess(result)" in text
    assert "provider_qr_url" not in text
    assert "innerHTML = ''" not in text
    assert "点击任务卡片后查看实时日志。" in text
    assert "concurrentEnabled" in text
    assert "concurrencyCount" in text
    assert "totalCount" in text
    assert "/api/tasks?page=1&page_size=" in text
    assert "/api/zc/claim" in text
    assert "autoClaimZc: false" in text
    assert "function errorText" in text
    assert "new Error(data.detail" not in text
    assert "data-job-id" in text
    assert ".task-card.active" in text
    assert "max-height:430px" in text


def test_main_index_task_table_supports_click_row_and_richer_logs():
    text = read_public_asset("index.html")
    assert 'href="/upi"' in text
    assert 'href="/upi/tasks"' in text
    assert 'data-open-task-log="${escapeHtml(item.job_id || "")}"' in text
    assert 'target.closest("button")' in text
    assert 'item.cs_id || item.job_id || item.status' in text
    assert 'function resolveTaskResultLink(data)' in text
    assert "const providerQrUrl = String(data.provider_qr_url || \"\").trim();" in text
    assert 'id="taskLogPanel"' not in text
    assert 'id="logModal"' in text
    assert ".modal-backdrop" in text
    assert ".modal-body" in text
    assert "function renderResultPreview" in text
    assert 'id="previewRow"' in text
    assert 'id="previewMedia"' in text
    assert '&provider=${encodeURIComponent(provider)}' in text


def test_console_shell_uses_registry_backed_two_level_navigation():
    shell_js = read_public_asset("assets/app-shell.js")
    shell_css = read_public_asset("assets/app-shell.css")
    operator_pages = [
        "index.html",
        "debug-generate.html",
        "stats.html",
        "qr.html",
        "kr-qr.html",
        "ch-qr.html",
        "in-qr.html",
        "nl-qr.html",
        "ph-qr.html",
        "settings.html",
        "upi.html",
        "upi-tasks.html",
        "upi-logs.html",
        "upi-result.html",
    ]

    for page in operator_pages:
        text = read_public_asset(page)
        assert "/assets/app-shell.css" in text
        assert "/assets/app-shell.js" in text
        assert "v=20260809-shell5" in text

    assert 'fetch("/api/providers"' in shell_js
    assert '["generate", "生成中心"]' in shell_js
    assert '["tasks", "任务中心"]' in shell_js
    assert '["queues", "支付队列"]' in shell_js
    assert '["debug", "调试工具"]' in shell_js
    assert '["stats", "运行统计"]' in shell_js
    assert '["settings", "配置"]' in shell_js
    assert 'korea: "kakao_pay"' in shell_js
    assert 'swiss: "twint"' in shell_js
    assert '"/ch-qr": "twint"' in shell_js
    assert '"/ph-qr": "gcash"' in shell_js
    assert 'return `/?provider=${publicType}&view=tasks`' in shell_js
    assert 'return `/settings?provider=${publicType}`' in shell_js
    assert 'document.body.dataset.paylinkSection = state.activeSection' in shell_js
    assert "function revealTab(container, tab)" in shell_js
    assert "scrollIntoView" not in shell_js
    assert "flex-wrap: nowrap" in shell_css
    assert "overflow-x: auto" in shell_css
    assert "white-space: nowrap" in shell_css
    brand_rules = shell_css.split(".paylink-app-shell__brand {", 1)[1].split("}", 1)[0]
    assert "min-height: 0" in brand_rules
    assert "padding: 0" in brand_rules
    assert "border-radius: 0" in brand_rules
    assert "background: transparent" in brand_rules
    assert '[data-paylink-section="generate"] #tasks' in shell_css
    assert '[data-paylink-section="tasks"] .control-column' in shell_css


def test_proxy_configuration_page_and_routes_exist():
    settings = read_public_asset("settings.html")
    settings_js = read_public_asset("assets/settings.js")
    route_paths = {route.path for route in app.app.routes}

    assert Path(app.SETTINGS_PAGE).exists()
    assert "/settings" in route_paths
    assert "/api/config/proxy" in route_paths
    assert "/api/config/proxy/test" in route_paths
    assert "/api/config/provider" in route_paths
    assert "/assets/app-shell.css?v=20260809-shell5" in settings
    assert "/assets/app-shell.js?v=20260809-shell5" in settings
    assert "/assets/settings.js" in settings
    assert 'id="paypalProfileSection"' in settings
    assert 'id="paypalCountry"' in settings
    assert 'id="saveProfileButton"' in settings
    assert 'fetch(`/api/config/proxy?provider=${encodeURIComponent(provider)}`' in settings_js
    assert 'fetch(`/api/config/provider?provider=${encodeURIComponent(provider)}`' in settings_js
    assert 'fetch("/api/config/proxy",' in settings_js
    assert 'fetch("/api/config/proxy/test",' in settings_js
    assert 'fetch("/api/config/provider",' in settings_js


def test_home_and_debug_pages_accept_public_provider_query_values():
    home = read_public_asset("index.html")
    debug = read_public_asset("debug-generate.html")

    assert '<option value="ideal">荷兰 iDEAL（NL / EUR）</option>' in home
    assert '<option value="gcash">菲律宾 GCash（PH / PHP）</option>' in home
    assert '<option value="grabpay">菲律宾 GrabPay（PH / PHP）</option>' in home
    assert '<option value="paypal">美国 PayPal（US / USD）</option>' in home
    assert '<option value="swiss">Twint（CH / CHF）</option>' in home
    assert 'gcash: {' in home
    assert 'grabpay: {' in home
    assert 'paypal: {' in home
    assert 'grabpay: "GrabPay"' in home
    assert 'paypal:["US","en"]' in debug
    assert 'swiss: "twint"' in home
    assert 'swiss: "twint"' in debug
    assert 'twint: "swiss"' in home
    assert 'twint: "swiss"' in debug
    assert 'new CustomEvent("paylink:provider-change"' in home
    assert 'new CustomEvent("paylink:provider-change"' in debug
    assert 'function currentConsoleView()' in home
    assert 'view === "tasks" ? "任务中心" : line.title' in home


def test_html_responses_disable_browser_storage_cache():
    async def html_response(_request):
        return Response("<html></html>", media_type="text/html")

    async def asset_response(_request):
        return Response("body {}", media_type="text/css")

    html = asyncio.run(app.disable_html_response_cache(request_for("/in-qr"), html_response))
    asset = asyncio.run(app.disable_html_response_cache(request_for("/assets/app-shell.css"), asset_response))

    assert html.headers["cache-control"] == "no-store, max-age=0"
    assert html.headers["pragma"] == "no-cache"
    assert html.headers["expires"] == "0"
    assert "cache-control" not in asset.headers


def test_upi_frontend_shell_assets_exist():
    upi_page = read_public_asset("upi.html")
    upi_tasks = read_public_asset("upi-tasks.html")
    upi_logs = read_public_asset("upi-logs.html")
    upi_result = read_public_asset("upi-result.html")
    upi_queue = read_public_asset("in-qr.html")
    upi_css = read_public_asset("assets/upi.css")
    upi_generate_js = read_public_asset("assets/upi-generate.js")
    upi_tasks_js = read_public_asset("assets/upi-tasks.js")
    upi_logs_js = read_public_asset("assets/upi-logs.js")

    assert "/assets/upi.css" in upi_page
    assert "/assets/upi-generate.js" in upi_page
    assert "/assets/upi-tasks.js" in upi_tasks
    assert "/assets/upi-logs.js" in upi_logs
    assert "OPLL-UPI" in upi_page
    assert "Task Queue" in upi_tasks
    assert "Live Logs" in upi_logs
    assert "Result Detail" in upi_result
    assert "OPLL-UPI" in upi_queue
    assert 'href="/upi/logs"' in upi_page
    assert 'href="/upi/logs"' in upi_tasks
    assert 'href="/upi/result"' in upi_page
    assert 'href="/upi/result"' in upi_tasks
    assert 'href="/upi/logs"' in upi_queue
    assert 'href="/upi/result"' in upi_queue
    assert 'href="/upi/tasks"' in upi_queue
    assert ".cli-output" in upi_css
    assert "/api/upi" in upi_generate_js
    assert "/api/upi/stream" in upi_generate_js
    assert "/api/upi/tasks" in upi_tasks_js
    assert "/api/upi/tasks/logs" in upi_tasks_js
    assert "/api/upi/tasks/logs" in upi_logs_js
    assert "/api/upi/queue" in read_public_asset("assets/provider-qr.js")


def test_zc_claim_request_uses_server_defaults():
    req = app.ZCClaimRequest(claimKey="debug-claim")

    assert req.base_url == ""
    assert req.claim_key == "debug-claim"


def test_confirm_payload_summary_cn_for_upi_requires_approval():
    summary = app.confirm_payload_summary_cn(
        {
            "account_settings": {},
            "application": "app",
            "submission_attempt": {"state": "requires_approval"},
            "payment_intent": {},
        },
        "upi",
    )

    text = " ".join(summary)
    assert "支付方式=upi" in text
    assert "提交状态=requires_approval" in text
    assert "下一步动作=无" in text
    assert "跳转链接=无" in text
    assert "SetupIntent=无" in text
    assert "响应字段=" in text
    assert "账号设置" in text
    assert "应用" in text


def test_stripe_confirm_success_log_is_chinese(monkeypatch):
    captured = {}

    def fake_log_event(kind, message, **kwargs):
        captured["kind"] = kind
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr(app, "log_event", fake_log_event)

    class Response:
        status_code = 200

    app.log_stripe_confirm_success(
        Response(),
        {
            "account_settings": {},
            "application": "app",
            "approval_method": "automatic",
            "automatic_payment_method_types": ["upi"],
            "billing_address_collection": "auto",
            "capture_method": "automatic",
            "cancel_url": "https://example.com/cancel",
            "submission_attempt": {"state": "requires_approval"},
        },
        {
            "guid": "g",
            "muid": "m",
            "sid": "s",
            "payment_method": "pm_123",
            "init_checksum": "abc",
            "version": "2024",
            "expected_amount": "100",
            "expected_payment_method_type": "upi",
        },
        "upi",
        job_id="job-1",
        cs_id="cs_1",
    )

    assert captured["kind"] == "protocol.stripe_confirm"
    assert "Stripe confirm 成功" in captured["message"]
    assert "HTTP状态=200" in captured["message"]
    assert "提交参数=" in captured["message"]
    assert "浏览器GUID" in captured["message"]
    assert "设备MUID" in captured["message"]
    assert "会话SID" in captured["message"]
    assert "支付方式ID" in captured["message"]
    assert "初始化校验" in captured["message"]
    assert "支付方式=upi" in captured["message"]
    assert "提交状态=requires_approval" in captured["message"]
    assert "响应字段=账号设置、应用、审批方式、自动支付方式、账单地址收集、取消地址、扣款方式" in captured["message"]


def test_debug_generate_routes_are_registered():
    routes = {route.path: getattr(route, "methods", set()) for route in app.app.routes}
    assert "/debug-generate" in routes
    assert "GET" in routes["/debug-generate"]
    assert "/api/debug/long-link" in routes
    assert "POST" in routes["/api/debug/long-link"]
    assert "/api/v1/upi" in routes
    assert "POST" in routes["/api/v1/upi"]
    assert "/api/v1/upi/stream" in routes
    assert "POST" in routes["/api/v1/upi/stream"]
    assert "/api/providers" in routes
    assert "GET" in routes["/api/providers"]


def test_provider_metadata_route_returns_enabled_registry_entries():
    route = next(route for route in app.app.routes if route.path == "/api/providers")
    response = route.endpoint()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["ok"] is True
    assert [item["public_type"] for item in payload["providers"]] == ["pix", "upi", "kakao_pay", "twint", "ideal", "gcash", "gopay", "grabpay", "paypal"]


def test_debug_generate_page_requires_admin_auth(monkeypatch):
    monkeypatch.setenv("OPLL_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.setenv("OPLL_AUTH_SECRET", "test-secret")

    response = app.debug_generate_page(request_for("/debug-generate"))

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?scope=admin")


def test_debug_generate_api_requires_admin_auth(monkeypatch):
    monkeypatch.setenv("OPLL_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.setenv("OPLL_AUTH_SECRET", "test-secret")

    with pytest.raises(HTTPException) as exc:
        app.generate_debug_long_link(
            request_for("/api/debug/long-link"),
            app.LongLinkRequest(job_id="debug-test", link_type="upi"),
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "auth required"


def test_api_v1_upi_requires_service_token(monkeypatch):
    monkeypatch.setattr(app, "UPI_SERVICE_TOKEN", "service-token")
    monkeypatch.setattr(app, "UPI_BUSINESS_TOKEN", "")
    monkeypatch.setattr(app, "UPI_FEATURE_ENABLED", True)
    monkeypatch.setattr(app, "UPI_PHONE_ONLY", False)

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/upi",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
        }
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(app.run_upi_api(req, app.UpiApiRequest(token="eyJ.a.b")))

    assert exc.value.status_code == 401


def test_extract_upi_api_request_validation_rejects_bad_token():
    with pytest.raises(HTTPException) as exc:
        app.validate_upi_api_request(app.UpiApiRequest(token="not-a-jwt"))

    assert exc.value.status_code == 400
    assert "invalid-token-format" in str(exc.value.detail)
