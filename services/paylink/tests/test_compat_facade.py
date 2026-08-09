from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paylink.compat_facade import CompatibilityFacade, ExtractRequest, normalize_result
from paylink.provider_config import ProviderConfigError
from paylink.provider_registry import enabled_provider_metadata, resolve_provider
from paylink.redact import redact_text, redact_value


class ProgressStore:
    def __init__(self) -> None:
        self.snapshots: dict[str, dict] = {}

    def set_progress(self, job_id: str, **values) -> None:
        previous = self.snapshots.get(job_id, {})
        snapshot = {"ok": True, "job_id": job_id, **previous, **values}
        self.snapshots[job_id] = snapshot

    def get_progress(self, job_id: str) -> dict:
        return dict(self.snapshots.get(job_id, {"ok": False}))


def _event_name(value: str) -> str:
    return value.split("\n", 1)[0].split(":", 1)[1].strip()


def _event_data(value: str) -> dict:
    return json.loads(value.split("data: ", 1)[1].strip())


@pytest.mark.parametrize(
    ("public_type", "native_type", "country", "locale"),
    [
        ("pix", "pix", "BR", "pt-BR"),
        ("upi", "upi", "IN", "en"),
        ("kakao_pay", "korea", "KR", "ko"),
        ("twint", "swiss", "CH", "de"),
        ("ideal", "ideal", "NL", "nl"),
        ("gcash", "gcash", "PH", "en-PH"),
        ("gopay", "gopay", "ID", "id"),
        ("grabpay", "grabpay", "PH", "en"),
        ("paypal", "paypal", "US", "en"),
    ],
)
def test_registry_resolves_first_release_providers(public_type, native_type, country, locale):
    resolved = resolve_provider(public_type)

    assert resolved.definition.native_type == native_type
    assert resolved.settings.country == country
    assert resolved.settings.locale == locale


def test_enabled_provider_metadata_exposes_console_routes():
    providers = enabled_provider_metadata()

    assert [item["public_type"] for item in providers] == ["pix", "upi", "kakao_pay", "twint", "ideal", "gcash", "gopay", "grabpay", "paypal"]
    assert [item["display_name"] for item in providers] == ["PIX", "UPI", "Kakao Pay", "Twint", "iDEAL", "GCash", "GoPay", "GrabPay", "PayPal"]
    assert [item["queue_path"] for item in providers] == ["/qr", "/in-qr", "/kr-qr", "/ch-qr", "/nl-qr", "/ph-qr", "/?provider=gopay&view=tasks", "/?provider=grabpay&view=tasks", "/?provider=paypal&view=tasks"]
    assert providers[2]["native_type"] == "korea"


def test_enabled_provider_metadata_omits_disabled_provider(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        """
[providers.pix]
enabled = true
country = BR
locale = pt-BR
[providers.upi]
enabled = false
country = IN
locale = en
[providers.kakao_pay]
enabled = true
country = KR
locale = ko
[providers.twint]
enabled = true
country = CH
locale = de
[providers.ideal]
enabled = true
country = NL
locale = nl
[providers.gcash]
enabled = true
country = PH
locale = en-PH
[providers.gopay]
enabled = true
country = ID
locale = id
[providers.grabpay]
enabled = true
country = PH
locale = en
[providers.paypal]
enabled = true
country = US
locale = en
""".strip(),
        encoding="utf-8",
    )

    providers = enabled_provider_metadata(config_path)

    assert [item["public_type"] for item in providers] == ["pix", "kakao_pay", "twint", "ideal", "gcash", "gopay", "grabpay", "paypal"]


def test_disabled_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.pix]\nenabled = false\ncountry = BR\nlocale = pt-BR\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("pix", config_path)


def test_disabled_paypal_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.paypal]\nenabled = false\ncountry = US\nlocale = en\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("paypal", config_path)


def test_disabled_twint_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.twint]\nenabled = false\ncountry = CH\nlocale = de\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("twint", config_path)


def test_disabled_gopay_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.gopay]\nenabled = false\ncountry = ID\nlocale = id\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("gopay", config_path)


def test_disabled_grabpay_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.grabpay]\nenabled = false\ncountry = PH\nlocale = en\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("grabpay", config_path)


def test_unknown_provider_is_rejected():
    with pytest.raises(ProviderConfigError, match="unsupported link_type"):
        resolve_provider("unknown")


def test_provider_missing_required_setting_is_rejected(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.pix]\nenabled = true\ncountry = \nlocale = pt-BR\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="country"):
        resolve_provider("pix", config_path)


def test_redaction_masks_proxy_credentials_and_access_tokens():
    text = redact_text("Bearer token-value http://user:pass@proxy.example.test:8080/path")
    value = redact_value({"access_token": "secret", "proxy": "http://user:pass@proxy.example.test:8080"})

    assert "token-value" not in text
    assert "user:pass" not in text
    assert value == {"access_token": "***", "proxy": "***"}


def test_facade_emits_one_result_then_done_without_persisting_access_token():
    store = ProgressStore()
    captured_requests = []
    logs = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    def generate_core(_request):
        return {
            "long_url": "https://pay.example.test/checkout",
            "provider_qr_url": "upi://pay?pa=merchant@example.test",
            "upi_qr_image_url": "https://pay.example.test/qr.png",
            "provider_qr_svg": "<svg></svg>",
            "provider_expires_at": 123,
            "payment_method_type": "upi",
        }

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=generate_core,
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda kind, message, **fields: logs.append((kind, message, fields)),
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="upi"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "upi"
    assert captured_requests[0]["billing_country"] == "IN"
    assert captured_requests[0]["accessToken"] == "access-token-123"
    assert store.snapshots[job_id]["link_type"] == "upi"
    assert "access-token-123" not in json.dumps(store.snapshots)
    assert all("access-token-123" not in str(item) for item in logs)
    assert [_event_name(item) for item in events][-2:] == ["result", "done"]
    result = _event_data(events[-2])["result"]
    assert result["payment_link_type"] == "upi"
    assert result["copy_paste"] == "upi://pay?pa=merchant@example.test"
    assert result["expires_at"] == 123


def test_facade_gcash_job_uses_native_ph_request_and_persists_public_type():
    store = ProgressStore()
    captured_requests = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=lambda _request: {
            "long_url": "https://payments.example.test/gcash",
            "provider_redirect_url": "https://payments.example.test/gcash",
            "payment_method_type": "gcash",
        },
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda *_args, **_kwargs: None,
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="gcash"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "gcash"
    assert captured_requests[0]["billing_country"] == "PH"
    assert captured_requests[0]["payment_locale"] == "en-PH"
    assert store.snapshots[job_id]["link_type"] == "gcash"
    result = _event_data(events[-2])["result"]
    assert result["payment_link_type"] == "gcash"
    assert result["payment_method"] == "gcash"


def test_facade_twint_job_uses_native_swiss_request_and_persists_public_type():
    store = ProgressStore()
    captured_requests = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=lambda _request: {
            "long_url": "https://payments.example.test/twint",
            "provider_redirect_url": "https://payments.example.test/twint",
            "payment_method_type": "twint",
        },
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda *_args, **_kwargs: None,
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="twint"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "swiss"
    assert captured_requests[0]["billing_country"] == "CH"
    assert captured_requests[0]["payment_locale"] == "de"
    assert store.snapshots[job_id]["link_type"] == "swiss"
    result = _event_data(events[-2])["result"]
    assert result["payment_link_type"] == "twint"
    assert result["payment_method"] == "twint"


def test_facade_gopay_job_uses_native_id_approval_request_and_persists_result():
    store = ProgressStore()
    captured_requests = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=lambda _request: {
            "long_url": "https://payments.example.test/gopay",
            "provider_redirect_url": "https://payments.example.test/gopay",
            "payment_method_type": "gopay",
            "approval_result": "approved",
            "submission_state": "requires_approval",
        },
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda *_args, **_kwargs: None,
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="gopay"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "gopay"
    assert captured_requests[0]["billing_country"] == "ID"
    assert captured_requests[0]["payment_locale"] == "id"
    assert store.snapshots[job_id]["link_type"] == "gopay"
    result = _event_data(events[-2])["result"]
    assert result["long_url"] == "https://payments.example.test/gopay"
    assert result["payment_link_type"] == "gopay"
    assert result["payment_method"] == "gopay"


def test_facade_grabpay_job_uses_native_ph_approval_request_and_persists_result():
    store = ProgressStore()
    captured_requests = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=lambda _request: {
            "long_url": "https://payments.example.test/grabpay",
            "provider_redirect_url": "https://payments.example.test/grabpay",
            "payment_method_type": "grabpay",
            "approval_result": "approved",
            "submission_state": "requires_approval",
        },
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda *_args, **_kwargs: None,
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="grabpay"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "grabpay"
    assert captured_requests[0]["billing_country"] == "PH"
    assert captured_requests[0]["payment_locale"] == "en"
    assert store.snapshots[job_id]["link_type"] == "grabpay"
    result = _event_data(events[-2])["result"]
    assert result["long_url"] == "https://payments.example.test/grabpay"
    assert result["payment_link_type"] == "grabpay"
    assert result["payment_method"] == "grabpay"


def test_facade_paypal_job_uses_standard_us_checkout_and_normalizes_result():
    store = ProgressStore()
    captured_requests = []

    def request_factory(**kwargs):
        captured_requests.append(dict(kwargs))
        return kwargs

    facade = CompatibilityFacade(
        request_factory=request_factory,
        generate_core=lambda _request: {
            "checkout_url": "https://checkout.example.test/paypal",
            "long_url": "https://checkout.example.test/paypal",
            "payment_method_type": "paypal",
        },
        set_progress=store.set_progress,
        get_progress=store.get_progress,
        log_event=lambda *_args, **_kwargs: None,
    )

    job_id = facade.create_job(ExtractRequest(token="access-token-123", link_type="paypal"))
    events = list(facade.iter_events(job_id))

    assert captured_requests[0]["link_type"] == "paypal"
    assert captured_requests[0]["billing_country"] == "US"
    assert captured_requests[0]["payment_locale"] == "en"
    assert store.snapshots[job_id]["link_type"] == "paypal"
    result = _event_data(events[-2])["result"]
    assert result["long_url"] == "https://checkout.example.test/paypal"
    assert result["payment_link_type"] == "paypal"
    assert result["payment_method"] == "paypal"


def test_normalize_result_falls_back_to_checkout_url():
    result = normalize_result({"checkout_url": "https://checkout.example.test", "payment_method_type": "pix"}, "pix")

    assert result["long_url"] == "https://checkout.example.test"
    assert result["payment_method"] == "pix"
    assert result["payment_link_type"] == "pix"
