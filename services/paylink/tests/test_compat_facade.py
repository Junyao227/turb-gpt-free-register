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
        ("ideal", "ideal", "NL", "nl"),
    ],
)
def test_registry_resolves_first_release_providers(public_type, native_type, country, locale):
    resolved = resolve_provider(public_type)

    assert resolved.definition.native_type == native_type
    assert resolved.settings.country == country
    assert resolved.settings.locale == locale


def test_enabled_provider_metadata_exposes_console_routes():
    providers = enabled_provider_metadata()

    assert [item["public_type"] for item in providers] == ["pix", "upi", "kakao_pay", "ideal"]
    assert [item["display_name"] for item in providers] == ["PIX", "UPI", "Kakao Pay", "iDEAL"]
    assert [item["queue_path"] for item in providers] == ["/qr", "/in-qr", "/kr-qr", "/nl-qr"]
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
[providers.ideal]
enabled = true
country = NL
locale = nl
""".strip(),
        encoding="utf-8",
    )

    providers = enabled_provider_metadata(config_path)

    assert [item["public_type"] for item in providers] == ["pix", "kakao_pay", "ideal"]


def test_disabled_provider_is_rejected_before_job_creation(tmp_path):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "[providers.pix]\nenabled = false\ncountry = BR\nlocale = pt-BR\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderConfigError, match="disabled"):
        resolve_provider("pix", config_path)


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
    assert "access-token-123" not in json.dumps(store.snapshots)
    assert all("access-token-123" not in str(item) for item in logs)
    assert [_event_name(item) for item in events][-2:] == ["result", "done"]
    result = _event_data(events[-2])["result"]
    assert result["payment_link_type"] == "upi"
    assert result["copy_paste"] == "upi://pay?pa=merchant@example.test"
    assert result["expires_at"] == 123


def test_normalize_result_falls_back_to_checkout_url():
    result = normalize_result({"checkout_url": "https://checkout.example.test", "payment_method_type": "pix"}, "pix")

    assert result["long_url"] == "https://checkout.example.test"
    assert result["payment_method"] == "pix"
    assert result["payment_link_type"] == "pix"
