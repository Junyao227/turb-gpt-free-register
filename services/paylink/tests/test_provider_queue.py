from pathlib import Path
import json
import sys
import pytest
from types import SimpleNamespace

from fastapi import HTTPException, Request

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


def test_checkout_request_body_disables_promo_for_korea():
    body = app.checkout_request_body(
        app.LongLinkRequest(
            link_type="korea",
            billing_country="KR",
            payment_locale="ko",
            use_promo_params=True,
        )
    )

    assert body["billing_details"] == {"country": "KR", "currency": "KRW"}
    assert body["checkout_ui_mode"] == "custom"
    assert "promo_campaign" not in body


def test_checkout_request_body_disables_initial_promo_for_pix():
    body = app.checkout_request_body(
        app.LongLinkRequest(
            link_type="pix",
            billing_country="BR",
            payment_locale="pt-BR",
            use_promo_params=True,
        )
    )

    assert body["billing_details"] == {"country": "BR", "currency": "BRL"}
    assert body["checkout_ui_mode"] == "custom"
    assert "promo_campaign" not in body


def test_provider_page_path_for_link_types():
    assert app.provider_page_path_for_link_type("korea") == "/kr-qr"
    assert app.provider_page_path_for_link_type("swiss") == "/ch-qr"
    assert app.provider_page_path_for_link_type("upi") == "/in-qr"
    assert app.provider_page_path_for_link_type("ideal") == "/nl-qr"
    assert app.provider_page_path_for_link_type("pix") == "/qr"


def test_ideal_line_mapping():
    req = app.LongLinkRequest(link_type="ideal", billing_country="NL", payment_locale="nl")

    assert app.normalize_link_type("nl") == "ideal"
    assert app.normalize_link_type("netherlands") == "ideal"
    assert app.normalize_provider_payment_method_type("ideal") == "ideal"
    assert app.payment_method_type_for_link_type("ideal") == "ideal"
    assert app.effective_country(req) == "NL"
    assert app.effective_payment_locale("ideal", req.payment_locale) == "nl"
    assert app.browser_timezone_for_link_type("ideal") == "Europe/Amsterdam"
    assert app.wallet_result_requires_provider_redirect("ideal") is True
    assert app.preferred_hosts_for_link_type("ideal") == ("ideal.nl",)


def test_ideal_payment_method_uses_bunq_bank():
    captured = {}

    class StripeStub:
        def post(self, url, data, timeout):
            captured["url"] = url
            captured["data"] = data
            captured["timeout"] = timeout
            return SimpleNamespace(status_code=200, json=lambda: {"id": "pm_test_ideal"})

    ctx = {
        "stripe_js_id": "stripe-js-id",
        "elements_session_id": "elements-session-id",
        "elements_session_config_id": "elements-config-id",
        "config_id": "checkout-config-id",
    }

    pm_id = app.stripe_create_payment_method(
        StripeStub(),
        "cs_test_ideal",
        "pk_test",
        app.billing_for_link_type("ideal"),
        "ideal",
        ctx,
    )

    assert pm_id == "pm_test_ideal"
    assert captured["url"] == "https://api.stripe.com/v1/payment_methods"
    assert captured["data"]["type"] == "ideal"
    assert captured["data"]["ideal[bank]"] == "bunq"
    assert captured["data"]["billing_details[address][country]"] == "NL"


def test_upi_line_mapping():
    req = app.LongLinkRequest(link_type="upi", billing_country="US", payment_locale="ja")

    assert app.normalize_link_type("india") == "upi"
    assert app.payment_method_type_for_link_type("upi") == "upi"
    assert app.effective_country(req) == "IN"
    assert app.effective_payment_locale("upi", req.payment_locale) == "en"
    assert app.browser_timezone_for_link_type("upi") == "Asia/Kolkata"


def test_gopay_line_mapping():
    req = app.LongLinkRequest(link_type="gopay", billing_country="US", payment_locale="en")

    assert app.normalize_link_type("gopay") == "gopay"
    assert app.normalize_provider_payment_method_type("indonesia") == "gopay"
    assert app.payment_method_type_for_link_type("gopay") == "gopay"
    assert app.effective_country(req) == "ID"
    assert app.effective_payment_locale("gopay", req.payment_locale) == "id"
    assert app.browser_timezone_for_link_type("gopay") == "Asia/Jakarta"


def test_gcash_line_mapping():
    req = app.LongLinkRequest(link_type="gcash", billing_country="US", payment_locale="en")

    assert app.normalize_link_type("gcash") == "gcash"
    assert app.payment_method_type_for_link_type("gcash") == "gcash"
    assert app.effective_country(req) == "PH"
    assert app.effective_payment_locale("gcash", req.payment_locale) == "en-PH"
    assert app.browser_timezone_for_link_type("gcash") == "Asia/Manila"


def test_grabpay_line_mapping():
    req = app.LongLinkRequest(link_type="grabpay", billing_country="US", payment_locale="en")

    assert app.normalize_link_type("grabpay") == "grabpay"
    assert app.payment_method_type_for_link_type("grabpay") == "grabpay"
    assert app.effective_country(req) == "PH"
    assert app.effective_payment_locale("grabpay", req.payment_locale) == "en-PH"
    assert app.browser_timezone_for_link_type("grabpay") == "Asia/Manila"


def test_gopay_checkout_request_body_and_headers_use_indonesia():
    req = app.LongLinkRequest(link_type="gopay", billing_country="US", payment_locale="en", accessToken="token")
    body = app.checkout_request_body(req)
    session = app.build_chatgpt_session(req)

    assert body["billing_details"] == {"country": "ID", "currency": "IDR"}
    assert session.headers["oai-language"] == "id-ID"
    assert "id-ID" in session.headers["Accept-Language"]


def test_gcash_checkout_request_body_and_headers_use_philippines():
    req = app.LongLinkRequest(link_type="gcash", billing_country="US", payment_locale="en", accessToken="token")
    body = app.checkout_request_body(req)
    session = app.build_chatgpt_session(req)

    assert body["billing_details"] == {"country": "PH", "currency": "PHP"}
    assert session.headers["oai-language"] == "en-PH"
    assert "en-PH" in session.headers["Accept-Language"]


def test_grabpay_checkout_request_body_and_headers_use_philippines():
    req = app.LongLinkRequest(link_type="grabpay", billing_country="US", payment_locale="en", accessToken="token")
    body = app.checkout_request_body(req)
    session = app.build_chatgpt_session(req)

    assert body["billing_details"] == {"country": "PH", "currency": "PHP"}
    assert session.headers["oai-language"] == "en-PH"
    assert "en-PH" in session.headers["Accept-Language"]


def test_provider_session_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RUNTIME_DIR", tmp_path)

    app.save_provider_pending_session(
        {
            "csId": "cs_test_1",
            "linkType": "korea",
            "providerRedirectUrl": "https://pay.nicepay.example/session",
            "longUrl": "https://pay.nicepay.example/session",
            "state": "pending",
        }
    )

    items = app.list_provider_pending_sessions("korea", limit=20)
    assert len(items) == 1
    assert items[0]["csId"] == "cs_test_1"
    assert items[0]["linkType"] == "korea"
    assert app.get_provider_pending_session("korea", "cs_test_1") is not None
    assert app.remove_provider_pending_session("korea", "cs_test_1") is True
    assert app.get_provider_pending_session("korea", "cs_test_1") is None


def test_upi_provider_session_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RUNTIME_DIR", tmp_path)

    app.save_provider_pending_session(
        {
            "csId": "cs_test_upi_1",
            "linkType": "upi",
            "qrUrl": "upi://pay?pa=merchant@example&pn=Merchant&am=10.00",
            "qrSvg": "<svg></svg>",
            "state": "pending",
        }
    )

    items = app.list_provider_pending_sessions("upi", limit=20)
    assert len(items) == 1
    assert items[0]["csId"] == "cs_test_upi_1"
    assert items[0]["linkType"] == "upi"
    assert items[0]["qrSvg"] == "<svg></svg>"
    assert app.get_provider_pending_session("upi", "cs_test_upi_1") is not None


def test_gopay_provider_session_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "RUNTIME_DIR", tmp_path)

    app.save_provider_pending_session(
        {
            "csId": "cs_test_gopay_1",
            "linkType": "gopay",
            "providerRedirectUrl": "https://checkout.midtrans.com/v2/gopay/session",
            "longUrl": "https://checkout.midtrans.com/v2/gopay/session",
            "state": "pending",
        }
    )

    items = app.list_provider_pending_sessions("gopay", limit=20)
    assert len(items) == 1
    assert items[0]["csId"] == "cs_test_gopay_1"
    assert items[0]["linkType"] == "gopay"
    assert app.get_provider_pending_session("gopay", "cs_test_gopay_1") is not None


def test_progress_snapshot_marks_gopay_blocked_as_failed():
    snapshot = {
        "ok": True,
        "job_id": "job_test_gopay_blocked",
        "done": True,
        "error": False,
        "text": "生成完成",
        "result": {
            "link_type": "gopay",
            "approval_result": "blocked",
            "provider_redirect_url": "",
            "provider_qr_url": "",
            "provider_qr_svg": "",
        },
    }

    assert app.progress_snapshot_failure_reason(snapshot) == "gopay approval did not succeed: blocked"


def test_progress_snapshot_marks_gopay_missing_redirect_as_failed():
    snapshot = {
        "ok": True,
        "job_id": "job_test_gopay_missing_redirect",
        "done": True,
        "error": False,
        "text": "生成完成",
        "result": {
            "link_type": "gopay",
            "approval_result": "approved",
            "provider_redirect_url": "",
            "provider_qr_url": "",
            "provider_qr_svg": "",
        },
    }

    assert app.progress_snapshot_failure_reason(snapshot) == "gopay provider redirect missing after approval"


def test_gopay_stripe_confirm_uses_checkout_style_payload(monkeypatch):
    recorded = {}

    class FakeStripe:
        def post(self, url, data=None, timeout=None):
            recorded["url"] = url
            recorded["data"] = dict(data or {})
            return SimpleNamespace(status_code=200, json=lambda: {"submission_attempt": {"state": "requires_approval"}})

    monkeypatch.setattr(app, "stripe_confirm_return_url", lambda *args, **kwargs: "https://chatgpt.com/return")
    monkeypatch.setattr(app, "stripe_init_gopay_checksum", lambda *args, **kwargs: "checksum_123")
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: None)

    payload = app.stripe_confirm(
        FakeStripe(),
        "cs_test_gopay",
        "pm_test_gopay",
        "pk_test_gopay",
        "gopay",
        {"total_summary": {"due": 12345}},
        {
            "runtime_version": "2025-test",
            "checkout_amount": "12345",
            "elements_session_id": "elements_session_test",
            "stripe_js_id": "stripe_js_test",
            "elements_session_config_id": "cfg_test",
            "config_id": "cfg_test",
            "locale": "id",
        },
        {
            "billing_country": "ID",
            "processor_entity": "openai_llc",
            "checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_gopay",
        },
        app.LongLinkRequest(link_type="gopay", payment_locale="id"),
        "",
        job_id="job-gopay-confirm",
    )

    body = recorded["data"]
    assert payload["submission_attempt"]["state"] == "requires_approval"
    assert body["expected_amount"] == "12345"
    assert body["elements_session_client[session_id]"] == "elements_session_test"
    assert body["elements_session_client[elements_init_source]"] == "custom_checkout"
    assert body["elements_session_client[stripe_js_id]"] == "stripe_js_test"
    assert body["client_attribution_metadata[checkout_session_id]"] == "cs_test_gopay"
    assert body["client_attribution_metadata[elements_session_id]"] == "elements_session_test"
    assert body["client_attribution_metadata[merchant_integration_source]"] == "checkout"
    assert body["_stripe_version"] == app.STRIPE_VERSION_FULL


def test_resolve_gopay_approval_fields_falls_through_to_redirect(monkeypatch):
    monkeypatch.setattr(app, "chatgpt_approve_result", lambda *args, **kwargs: "approved")
    monkeypatch.setattr(app, "stripe_payment_page_redirect_url", lambda *args, **kwargs: "https://hooks.stripe.com/redirect/gopay")
    monkeypatch.setattr(app, "resolve_external_redirect", lambda *args, **kwargs: "https://app.midtrans.com/gopay/pay/test")

    fields = app.resolve_gopay_approval_fields(
        {
            "confirm_payload": {"submission_attempt": {"state": "requires_approval"}},
            "cs_id": "cs_test_gopay",
            "job_id": "job_test_gopay",
            "link_type": "gopay",
            "pm_id": "pm_test_gopay",
            "stripe_pk": "pk_test_gopay",
        },
        {"checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_gopay"},
        {
            "chatgpt": object(),
            "req": app.LongLinkRequest(link_type="gopay", payment_locale="id"),
            "stripe": object(),
        },
    )

    assert fields["payment_method_id"] == "pm_test_gopay"
    assert fields["stripe_redirect_url"] == "https://hooks.stripe.com/redirect/gopay"
    assert fields["provider_redirect_url"] == "https://app.midtrans.com/gopay/pay/test"
    assert fields["long_url"] == "https://app.midtrans.com/gopay/pay/test"
    assert fields["approval_result"] == "approved"
    assert fields["submission_state"] == "requires_approval"
    assert fields["completion_stage"] == "provider_redirect_ready"


def test_resolve_gopay_approval_fields_rejects_non_gopay_provider_host(monkeypatch):
    monkeypatch.setattr(app, "chatgpt_approve_result", lambda *args, **kwargs: "approved")
    monkeypatch.setattr(app, "stripe_payment_page_redirect_url", lambda *args, **kwargs: "https://hooks.stripe.com/redirect/gopay")
    monkeypatch.setattr(app, "resolve_external_redirect", lambda *args, **kwargs: "https://example.com/not-gopay")

    with pytest.raises(HTTPException) as exc:
        app.resolve_gopay_approval_fields(
            {
                "confirm_payload": {"submission_attempt": {"state": "requires_approval"}},
                "cs_id": "cs_test_gopay",
                "job_id": "job_test_gopay",
                "link_type": "gopay",
                "pm_id": "pm_test_gopay",
                "stripe_pk": "pk_test_gopay",
            },
            {"checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_gopay"},
            {
                "chatgpt": object(),
                "req": app.LongLinkRequest(link_type="gopay", payment_locale="id"),
                "stripe": object(),
            },
        )

    assert exc.value.status_code == 502
    assert "host mismatch" in str(exc.value.detail)


def test_resolve_gopay_approval_fields_rejects_missing_provider_redirect(monkeypatch):
    monkeypatch.setattr(app, "chatgpt_approve_result", lambda *args, **kwargs: "approved")
    monkeypatch.setattr(app, "stripe_payment_page_redirect_url", lambda *args, **kwargs: "https://hooks.stripe.com/redirect/gopay")
    monkeypatch.setattr(app, "resolve_external_redirect", lambda *args, **kwargs: "")

    with pytest.raises(HTTPException) as exc:
        app.resolve_gopay_approval_fields(
            {
                "confirm_payload": {"submission_attempt": {"state": "requires_approval"}},
                "cs_id": "cs_test_gopay",
                "job_id": "job_test_gopay",
                "link_type": "gopay",
                "pm_id": "pm_test_gopay",
                "stripe_pk": "pk_test_gopay",
            },
            {"checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_gopay"},
            {
                "chatgpt": object(),
                "req": app.LongLinkRequest(link_type="gopay", payment_locale="id"),
                "stripe": object(),
            },
        )

    assert exc.value.status_code == 502
    assert "redirect missing" in str(exc.value.detail)


def test_provider_pending_rejects_gopay(monkeypatch):
    monkeypatch.delenv("OPLL_QR_PASSWORD", raising=False)
    monkeypatch.delenv("OPLL_AUTH_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc:
        app.provider_pending(request_for("/api/provider/pending"), link_type="gopay", limit=20)

    assert exc.value.status_code == 400


def test_upi_qr_details_from_next_action(monkeypatch):
    monkeypatch.setattr(app, "render_qr_svg", lambda value: f"<svg>{value}</svg>")

    details = app.extract_upi_qr_details(
        {
            "payment_intent": {
                "next_action": {
                    "type": "upi_display_qr_code",
                    "upi_display_qr_code": {
                        "data": "upi://pay?pa=merchant@example",
                        "expires_at": 1781191857,
                    },
                }
            }
        }
    )

    assert details["provider_qr_url"] == "upi://pay?pa=merchant@example"
    assert details["provider_qr_svg"] == "<svg>upi://pay?pa=merchant@example</svg>"
    assert details["provider_expires_at"] == 1781191857


def test_build_upi_provider_fields_does_not_require_redirect():
    fields = app.build_upi_provider_fields(
        "pm_test_upi",
        {"checkout_url": "https://chatgpt.com/checkout/cs_test_upi"},
        {
            "provider_qr_url": "upi://pay?pa=merchant@example",
            "provider_qr_svg": "<svg></svg>",
            "provider_expires_at": 1781191857,
        },
    )

    assert fields["payment_method_id"] == "pm_test_upi"
    assert fields["provider_redirect_url"] == ""
    assert fields["long_url"] == "https://chatgpt.com/checkout/cs_test_upi"
    assert fields["provider_qr_url"] == "upi://pay?pa=merchant@example"
    assert fields["provider_qr_svg"] == "<svg></svg>"


def test_extract_upi_qr_details_supports_handle_redirect_qr_code_shape():
    details = app.extract_upi_qr_details(
        {
            "next_action": {
                "type": "upi_handle_redirect_or_display_qr_code",
                "upi_handle_redirect_or_display_qr_code": {
                    "hosted_instructions_url": "https://hooks.stripe.com/upi/session",
                    "qr_code": {
                        "data": "upi://pay?pa=merchant@example",
                        "image_url_png": "https://stripe.example/upi.png",
                        "image_url_svg": "https://stripe.example/upi.svg",
                        "expires_at": 1781191857,
                    },
                },
            }
        }
    )

    assert details["provider_qr_url"] == "upi://pay?pa=merchant@example"
    assert details["provider_qr_image_url"] == "https://stripe.example/upi.png"
    assert "<svg" in details["provider_qr_svg"]
    assert details["provider_expires_at"] == 1781191857


def test_extract_upi_success_result_supports_redirect_to_url():
    result = app.extract_upi_success_result(
        {
            "next_action": {
                "type": "redirect_to_url",
                "redirect_to_url": {
                    "url": "https://hooks.stripe.com/upi/authorize/test",
                },
            }
        }
    )

    assert result["next_action_type"] == "redirect_to_url"
    assert result["upi_redirect_url"] == "https://hooks.stripe.com/upi/authorize/test"
    assert result["provider_redirect_url"] == "https://hooks.stripe.com/upi/authorize/test"


def test_extract_upi_success_result_supports_display_upi_qr_code_hosted_url():
    result = app.extract_upi_success_result(
        {
            "next_action": {
                "type": "display_upi_qr_code",
                "display_upi_qr_code": {
                    "data": "upi://pay?pa=merchant@example",
                    "image_url_png": "https://stripe.example/upi.png",
                    "hosted_instructions_url": "https://hooks.stripe.com/upi/hosted/test",
                },
            }
        }
    )

    assert result["next_action_type"] == "display_upi_qr_code"
    assert result["upi_qr_data"] == "upi://pay?pa=merchant@example"
    assert result["upi_qr_image_url"] == "https://stripe.example/upi.png"
    assert result["upi_hosted_url"] == "https://hooks.stripe.com/upi/hosted/test"


def test_extract_upi_success_result_supports_hosted_instructions_without_qr():
    result = app.extract_upi_success_result(
        {
            "next_action": {
                "type": "display_upi_qr_code",
                "hosted_instructions_url": "https://payments.stripe.com/upi/instructions/test",
            }
        }
    )

    assert result["upi_hosted_url"] == "https://payments.stripe.com/upi/instructions/test"
    assert result["provider_qr_url"] == ""


def test_payment_page_terminal_failure_includes_nested_error_code():
    reason = app.payment_page_terminal_failure(
        {
            "submission_attempt": {
                "state": "failed",
                "error": {
                    "code": "checkout_upcoming_invoice_mismatch",
                    "payment_error": None,
                },
            }
        }
    )

    assert reason == "state=failed code=checkout_upcoming_invoice_mismatch"


def test_checkout_challenge_error_uses_compact_summary():
    response = SimpleNamespace(
        status_code=403,
        headers={"Content-Type": "text/html", "cf-mitigated": "challenge"},
        text="<html><body>Bearer challenge-token " + ("x" * 1200) + "</body></html>",
    )

    with pytest.raises(HTTPException) as exc:
        app.parse_checkout_response(response, app.LongLinkRequest(link_type="pix"))

    assert exc.value.status_code == 503
    assert exc.value.detail == "checkout challenge blocked: HTTP 403 HTML response"
    assert "<html" not in str(exc.value.detail).lower()
    assert "challenge-token" not in str(exc.value.detail)


def test_checkout_error_summary_redacts_and_bounds_json_body():
    response = SimpleNamespace(
        status_code=400,
        headers={"Content-Type": "application/json"},
        text=json.dumps({"access_token": "private-token", "message": "invalid checkout"}),
    )

    with pytest.raises(HTTPException) as exc:
        app.parse_checkout_response(response, app.LongLinkRequest(link_type="pix"))

    detail = str(exc.value.detail)
    assert exc.value.status_code == 400
    assert detail.startswith("checkout create failed: HTTP 400")
    assert "private-token" not in detail
    assert '"access_token": "***"' in detail


def test_upi_payment_page_stops_immediately_on_terminal_failure(monkeypatch):
    class Response:
        status_code = 200
        headers = {}

        @staticmethod
        def json():
            return {
                "submission_attempt": {
                    "state": "failed",
                    "error": {"code": "checkout_upcoming_invoice_mismatch"},
                }
            }

    class Stripe:
        @staticmethod
        def get(*_args, **_kwargs):
            return Response()

    monkeypatch.setattr(app, "log_protocol_capture", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc:
        app.stripe_payment_page_upi_details(
            Stripe(),
            "cs_test_upi",
            "pk_test_upi",
            app.LongLinkRequest(link_type="upi"),
            job_id="job_test_upi",
            timeout_seconds=30,
        )

    assert exc.value.status_code == 502
    assert "checkout_upcoming_invoice_mismatch" in str(exc.value.detail)


def test_upi_terminal_payment_failure_is_not_retryable():
    response = app.upi_error_response_from_exception(
        HTTPException(
            status_code=502,
            detail="upi payment failed: state=failed code=checkout_upcoming_invoice_mismatch",
        )
    )
    payload = json.loads(response.body)

    assert payload["reason"] == "confirm-failed"
    assert payload["retryable"] is False


def test_build_pix_provider_fields_prefers_hosted_url_over_checkout_and_qr():
    fields = app.build_pix_provider_fields(
        "pm_test_pix",
        {"checkout_url": "https://chatgpt.com/checkout/cs_test_pix"},
        {
            "pix_hosted_instructions_url": "https://payments.stripe.com/pix/instructions/test",
            "pix_qr_image_url_png": "https://qr.stripe.com/pix.png",
        },
    )

    assert fields["long_url"] == "https://payments.stripe.com/pix/instructions/test"
    assert fields["provider_redirect_url"] == "https://payments.stripe.com/pix/instructions/test"


def test_build_upi_provider_fields_prefers_hosted_url_over_qr():
    fields = app.build_upi_provider_fields(
        "pm_test_upi",
        {"checkout_url": "https://chatgpt.com/checkout/cs_test_upi"},
        {
            "upi_hosted_url": "https://payments.stripe.com/upi/instructions/test",
            "provider_qr_url": "https://qr.stripe.com/upi.png",
        },
    )

    assert fields["long_url"] == "https://payments.stripe.com/upi/instructions/test"
    assert fields["provider_qr_url"] == "https://qr.stripe.com/upi.png"


def test_resolve_upi_provider_fields_approval_uses_job_id_and_payment_page(monkeypatch):
    calls = {"approve_pool": [], "payment_page": []}

    def fake_chatgpt_approve_pool(chatgpt, cs_id, checkout, *, pool_keep, pool_max, job_id=""):
        calls["approve_pool"].append((cs_id, checkout["billing_country"], pool_keep, pool_max, job_id))
        return "approved"

    def fake_payment_page_upi_details(stripe, cs_id, stripe_pk, req, job_id="", timeout_seconds=30):
        calls["payment_page"].append((cs_id, stripe_pk, req.link_type, job_id, timeout_seconds))
        return {
            "provider_qr_url": "upi://pay?pa=merchant@example",
            "provider_qr_svg": "<svg>upi://pay?pa=merchant@example</svg>",
            "provider_qr_image_url": "",
            "provider_expires_at": 1781191857,
        }

    monkeypatch.setattr(app, "chatgpt_approve_pool", fake_chatgpt_approve_pool)
    monkeypatch.setattr(app, "stripe_payment_page_upi_details", fake_payment_page_upi_details)
    monkeypatch.setattr(app, "extract_upi_success_result", lambda payload: {})

    fields = app.resolve_upi_provider_fields(
        {
            "confirm_payload": {"submission_attempt": {"state": "requires_approval"}},
            "cs_id": "cs_test_upi",
            "job_id": "job_test_upi",
            "link_type": "upi",
            "pm_id": "pm_test_upi",
            "stripe_pk": "pk_test_upi",
            "pool_keep": 7,
            "pool_max": 123,
        },
        {"checkout_url": "https://chatgpt.com/checkout/cs_test_upi", "billing_country": "IN", "processor_entity": "openai_ie"},
        {
            "chatgpt": object(),
            "req": app.LongLinkRequest(link_type="upi", payment_locale="en"),
            "stripe": object(),
        },
    )

    assert calls["approve_pool"] == [("cs_test_upi", "IN", 7, 123, "job_test_upi")]
    assert calls["payment_page"] == [("cs_test_upi", "pk_test_upi", "upi", "job_test_upi", 45)]
    assert fields["provider_qr_url"] == "upi://pay?pa=merchant@example"
    assert fields["provider_qr_svg"] == "<svg>upi://pay?pa=merchant@example</svg>"
