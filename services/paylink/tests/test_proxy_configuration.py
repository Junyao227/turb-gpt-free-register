import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from paylink import provider_config


FIXTURE_PROXY = "http://fixture-user:fixture-pass@proxy.example.test:443"
FIXTURE_PROXY_TWO = "http://fixture-user-two:fixture-pass-two@proxy-two.example.test:8443"


def configure_paypal_profile(monkeypatch, tmp_path, country="US", locale="en"):
    config_path = tmp_path / "providers.ini"
    config_path.write_text(
        "\n".join(
            (
                "# retained top-level comment",
                "[providers.paypal]",
                "enabled = true",
                f"country = {country}",
                f"locale = {locale}",
                "custom_option = retain-me",
                "",
                "[providers.other]",
                "enabled = true",
                "country = US",
                "locale = en",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_config, "DEFAULT_CONFIG_PATH", config_path)
    return config_path


def test_proxy_config_view_masks_provider_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY_POOL", f"{FIXTURE_PROXY};{FIXTURE_PROXY_TWO}")

    view = app.proxy_config_view("gcash")
    serialized = json.dumps(view)

    assert view["fallback"] == {
        "env_key": "OPENAI_PAY_PH_PROXY",
        "configured": True,
        "masked_value": "configured",
    }
    assert view["pool"]["env_key"] == "OPENAI_PAY_PH_PROXY_POOL"
    assert view["pool"]["configured"] is True
    assert view["pool"]["count"] == 2
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_proxy_config_view_maps_us_paypal_to_legacy_dedicated_settings(monkeypatch, tmp_path):
    configure_paypal_profile(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_PROXY_POOL", FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("paypal")
    serialized = json.dumps(view)

    assert view["fallback"]["env_key"] == "OPENAI_PAY_PAYPAL_PROXY"
    assert view["pool"]["env_key"] == "OPENAI_PAY_PAYPAL_PROXY_POOL"
    assert view["pool"]["count"] == 1
    assert [item["stage"] for item in view["visible_stages"]] == ["provider", "promotion"]
    assert view["visible_stages"][0]["label"] == "主池 / PayPal Checkout"
    assert view["visible_stages"][0]["role"] == "checkout_provider_approve"
    assert view["profile"] == {
        "country": "US",
        "locale": "en",
        "currency": "USD",
        "fallback_key": "OPENAI_PAY_PAYPAL_PROXY",
        "pool_key": "OPENAI_PAY_PAYPAL_PROXY_POOL",
    }
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized
    profile_view = app.provider_profile_config_view("paypal")
    assert [item["locale"] for item in profile_view["locale_choices"]] == ["en", "th", "pt-BR"]


@pytest.mark.parametrize(
    ("country", "locale", "currency"),
    (("TH", "th", "THB"), ("BR", "pt-BR", "BRL")),
)
def test_proxy_config_view_uses_active_regional_paypal_settings(monkeypatch, tmp_path, country, locale, currency):
    configure_paypal_profile(monkeypatch, tmp_path, country, locale)
    fallback_key = f"OPENAI_PAY_PAYPAL_{country}_PROXY"
    pool_key = f"OPENAI_PAY_PAYPAL_{country}_PROXY_POOL"
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_PROXY", "http://legacy-user:legacy-pass@legacy.example.test:443")
    monkeypatch.setenv(fallback_key, FIXTURE_PROXY)
    monkeypatch.setenv(pool_key, FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("paypal")
    serialized = json.dumps(view)

    assert view["fallback"]["env_key"] == fallback_key
    assert view["pool"]["env_key"] == pool_key
    assert view["pool"]["count"] == 1
    assert view["profile"]["country"] == country
    assert view["profile"]["locale"] == locale
    assert view["profile"]["currency"] == currency
    assert [item["stage"] for item in view["visible_stages"]] == ["provider", "promotion"]
    assert view["visible_stages"][0]["fallback"]["env_key"] == fallback_key
    assert "fixture-user" not in serialized
    assert "legacy-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_proxy_config_view_maps_twint_to_existing_swiss_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_SWISS_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_SWISS_PROXY_POOL", FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("twint")
    serialized = json.dumps(view)

    assert view["native_type"] == "swiss"
    assert view["fallback"]["env_key"] == "OPENAI_PAY_SWISS_PROXY"
    assert view["pool"]["env_key"] == "OPENAI_PAY_SWISS_PROXY_POOL"
    assert view["pool"]["count"] == 1
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_proxy_config_view_maps_gopay_to_its_approval_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_GOPAY_PROVIDER_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL", FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("gopay")
    serialized = json.dumps(view)

    assert view["native_type"] == "gopay"
    assert view["fallback"]["env_key"] == "OPENAI_PAY_GOPAY_PROVIDER_PROXY"
    assert view["pool"]["env_key"] == "OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL"
    assert view["pool"]["count"] == 1
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_proxy_config_view_maps_grabpay_to_its_dedicated_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_GRABPAY_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_GRABPAY_PROXY_POOL", FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("grabpay")
    serialized = json.dumps(view)

    assert view["native_type"] == "grabpay"
    assert view["fallback"]["env_key"] == "OPENAI_PAY_GRABPAY_PROXY"
    assert view["pool"]["env_key"] == "OPENAI_PAY_GRABPAY_PROXY_POOL"
    assert view["pool"]["count"] == 1
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_provider_proxy_runtime_mapping_covers_swiss_gopay_and_grabpay_settings():
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_SWISS_PROXY"] == "SWISS_STAGE_PROXY"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_SWISS_PROXY_POOL"] == "SWISS_PROXY_POOL"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GOPAY_PROVIDER_PROXY"] == "GOPAY_PROVIDER_STAGE_PROXY"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL"] == "GOPAY_PROVIDER_PROXY_POOL"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GRABPAY_PROXY"] == "GRABPAY_STAGE_PROXY"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GRABPAY_PROXY_POOL"] == "GRABPAY_PROXY_POOL"


def test_proxy_configuration_update_writes_atomically_and_updates_runtime(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("UNRELATED_VALUE=keep\nOPENAI_PAY_PH_PROXY=old-value\n", encoding="utf-8")
    monkeypatch.setattr(app, "PAYLINK_ENV_PATH", env_path)
    monkeypatch.setattr(app, "PH_STAGE_PROXY", "")
    monkeypatch.setattr(app, "PH_PROXY_POOL", [])
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY", "")
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY_POOL", "")

    result = app.update_provider_proxy_config(
        app.ProviderProxyUpdateRequest(
            provider="gcash",
            fallbackProxy=FIXTURE_PROXY,
            proxyPool=f"{FIXTURE_PROXY_TWO}\n{FIXTURE_PROXY}",
        )
    )
    content = env_path.read_text(encoding="utf-8")

    assert "UNRELATED_VALUE=keep" in content
    assert f'OPENAI_PAY_PH_PROXY="{FIXTURE_PROXY}"' in content
    assert f'OPENAI_PAY_PH_PROXY_POOL="{FIXTURE_PROXY_TWO};{FIXTURE_PROXY}"' in content
    assert app.PH_STAGE_PROXY == FIXTURE_PROXY
    assert app.PH_PROXY_POOL == [FIXTURE_PROXY_TWO, FIXTURE_PROXY]
    assert "fixture-user" not in json.dumps(result)


def test_paypal_profile_update_preserves_unrelated_ini_content_and_switches_proxy_view(monkeypatch, tmp_path):
    config_path = configure_paypal_profile(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_TH_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_TH_PROXY_POOL", FIXTURE_PROXY_TWO)

    result = app.update_provider_profile_config(
        app.ProviderProfileUpdateRequest(provider="paypal", country="TH", locale="en")
    )
    content = config_path.read_text(encoding="utf-8")

    assert result["config"]["country"] == "TH"
    assert result["config"]["locale"] == "en"
    assert "# retained top-level comment" in content
    assert "custom_option = retain-me" in content
    assert "[providers.other]" in content
    assert "country = TH" in content
    assert "locale = en" in content
    assert app.proxy_config_view("paypal")["fallback"]["env_key"] == "OPENAI_PAY_PAYPAL_TH_PROXY"
    assert not list(tmp_path.glob(".providers-*.tmp"))


def test_paypal_profile_validation_does_not_change_ini(monkeypatch, tmp_path):
    config_path = configure_paypal_profile(monkeypatch, tmp_path)
    original = config_path.read_text(encoding="utf-8")
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)

    with pytest.raises(app.HTTPException, match="unsupported PayPal locale") as exc:
        app.update_provider_profile_config(
            app.ProviderProfileUpdateRequest(provider="paypal", country="BR", locale="ja")
        )

    assert exc.value.status_code == 400
    assert config_path.read_text(encoding="utf-8") == original

    with pytest.raises(app.HTTPException, match="country profile is required"):
        app.update_provider_profile_config(app.ProviderProfileUpdateRequest(provider="paypal"))

    assert config_path.read_text(encoding="utf-8") == original


def test_regional_paypal_proxy_update_writes_dynamic_env_keys_and_reads_them_at_runtime(monkeypatch, tmp_path):
    configure_paypal_profile(monkeypatch, tmp_path, "BR", "pt-BR")
    env_path = tmp_path / ".env"
    env_path.write_text("UNRELATED_VALUE=keep\n", encoding="utf-8")
    monkeypatch.setattr(app, "PAYLINK_ENV_PATH", env_path)
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_BR_PROXY", "")
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_BR_PROXY_POOL", "")

    result = app.update_provider_proxy_config(
        app.ProviderProxyUpdateRequest(
            provider="paypal",
            fallbackProxy=FIXTURE_PROXY,
            proxyPool=FIXTURE_PROXY_TWO,
        )
    )

    assert 'OPENAI_PAY_PAYPAL_BR_PROXY="http://fixture-user:fixture-pass@proxy.example.test:443"' in env_path.read_text(encoding="utf-8")
    assert app.proxy_candidates_for_request(
        app.LongLinkRequest(link_type="paypal", billing_country="BR", payment_locale="pt-BR")
    ) == [FIXTURE_PROXY_TWO, FIXTURE_PROXY]
    assert result["config"]["fallback"]["env_key"] == "OPENAI_PAY_PAYPAL_BR_PROXY"
    assert "fixture-user" not in json.dumps(result)


def test_grabpay_proxy_configuration_updates_its_dedicated_runtime(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("UNRELATED_VALUE=keep\n", encoding="utf-8")
    monkeypatch.setattr(app, "PAYLINK_ENV_PATH", env_path)
    monkeypatch.setattr(app, "GRABPAY_STAGE_PROXY", "")
    monkeypatch.setattr(app, "GRABPAY_PROXY_POOL", [])
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENAI_PAY_GRABPAY_PROXY", "")
    monkeypatch.setenv("OPENAI_PAY_GRABPAY_PROXY_POOL", "")

    result = app.update_provider_proxy_config(
        app.ProviderProxyUpdateRequest(
            provider="grabpay",
            fallbackProxy=FIXTURE_PROXY,
            proxyPool=FIXTURE_PROXY_TWO,
        )
    )
    content = env_path.read_text(encoding="utf-8")

    assert "UNRELATED_VALUE=keep" in content
    assert f'OPENAI_PAY_GRABPAY_PROXY="{FIXTURE_PROXY}"' in content
    assert f'OPENAI_PAY_GRABPAY_PROXY_POOL="{FIXTURE_PROXY_TWO}"' in content
    assert app.GRABPAY_STAGE_PROXY == FIXTURE_PROXY
    assert app.GRABPAY_PROXY_POOL == [FIXTURE_PROXY_TWO]
    assert "fixture-user" not in json.dumps(result)


def test_invalid_proxy_leaves_existing_env_file_unchanged(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    original = "UNRELATED_VALUE=keep\n"
    env_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(app, "PAYLINK_ENV_PATH", env_path)
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)

    with pytest.raises(app.HTTPException) as exc:
        app.update_provider_proxy_config(
            app.ProviderProxyUpdateRequest(provider="gcash", fallbackProxy="fixture proxy")
        )

    assert exc.value.status_code == 400
    assert env_path.read_text(encoding="utf-8") == original


def test_proxy_connectivity_test_uses_only_dedicated_config_and_redacts_logs(monkeypatch):
    calls = []
    logs = []

    class Response:
        status_code = 204

    class Session:
        proxies = {}

        def get(self, url, timeout):
            calls.append((url, timeout, dict(self.proxies)))
            return Response()

        def close(self):
            calls.append(("close",))

    monkeypatch.setenv("OPENAI_PAY_PH_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY_POOL", "")
    monkeypatch.setattr(app.requests, "Session", Session)
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: logs.append((args, kwargs)))

    result = app.provider_proxy_connectivity_test("gcash")
    serialized = json.dumps({"result": result, "logs": logs})

    assert result["ok"] is True
    assert calls[0][0] == app.PROXY_TEST_URL
    assert calls[0][1] == app.PROXY_TEST_TIMEOUT
    assert calls[0][2]["https"] == FIXTURE_PROXY
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_proxy_connectivity_requires_dedicated_proxy(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY", "")
    monkeypatch.setenv("OPENAI_PAY_PH_PROXY_POOL", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY", FIXTURE_PROXY)
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [FIXTURE_PROXY])

    with pytest.raises(app.HTTPException) as exc:
        app.provider_proxy_connectivity_test("gcash")

    assert exc.value.status_code == 400


def test_dedicated_ideal_proxy_pool_has_precedence_over_generic_fallback(monkeypatch):
    ideal_proxy = "http://fixture-ideal:fixture-pass@ideal-proxy.example.test:443"
    generic_proxy = "http://fixture-generic:fixture-pass@generic-proxy.example.test:443"
    monkeypatch.setattr(app, "IDEAL_PROXY_POOL", [ideal_proxy])
    monkeypatch.setattr(app, "IDEAL_STAGE_PROXY", "")
    monkeypatch.setattr(app, "PROVIDER_PROXY_POOL", [generic_proxy])
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", generic_proxy)
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "DEFAULT_PROXY", "")

    candidates = app.proxy_candidates_for_link_type("", "ideal")

    assert candidates[0] == ideal_proxy
    assert generic_proxy in candidates[1:]


def test_dedicated_us_paypal_proxy_pool_has_precedence_over_generic_checkout_candidates(monkeypatch, tmp_path):
    configure_paypal_profile(monkeypatch, tmp_path)
    paypal_proxy = "http://fixture-paypal:fixture-pass@paypal-proxy.example.test:443"
    generic_proxy = "http://fixture-generic:fixture-pass@generic-proxy.example.test:443"
    monkeypatch.setattr(app, "PAYPAL_PROXY_POOL", [paypal_proxy])
    monkeypatch.setattr(app, "PAYPAL_STAGE_PROXY", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [generic_proxy])
    monkeypatch.setattr(app, "DEFAULT_PROXY", generic_proxy)

    candidates = app.proxy_candidates_for_link_type("", "paypal")

    assert candidates[0] == paypal_proxy
    assert generic_proxy in candidates[1:]


@pytest.mark.parametrize(
    ("provider", "expected_stages"),
    (
        ("paypal", ("provider", "promotion")),
        ("upi", ("checkout", "promotion", "provider")),
        ("pix", ("checkout", "promotion", "provider")),
        ("ideal", ("checkout", "promotion", "provider")),
        ("kakao_pay", ("checkout", "promotion", "provider")),
        ("gcash", ("checkout", "promotion", "provider")),
        ("gopay", ("checkout", "promotion", "provider")),
        ("grabpay", ("checkout", "promotion", "provider")),
    ),
)
def test_primary_provider_visible_proxy_stages_follow_fixed_reference_contracts(
    monkeypatch,
    tmp_path,
    provider,
    expected_stages,
):
    if provider == "paypal":
        configure_paypal_profile(monkeypatch, tmp_path)

    view = app.proxy_config_view(provider)

    assert tuple(item["stage"] for item in view["visible_stages"]) == expected_stages
    assert all(item["stage"] != "approve" for item in view["visible_stages"])
    if provider == "paypal":
        assert [item["label"] for item in view["visible_stages"]] == [
            "主池 / PayPal Checkout",
            "优惠池 / checkout update",
        ]
    else:
        assert any(item["role"] == "promotion_update" for item in view["visible_stages"])


def test_proxy_region_rewrite_supports_live_provider_formats():
    assert (
        app.proxy_for_region(
            "http://fixture-user-region-JP-sid-demo-t-5:fixture-pass@proxy.example.test:443",
            "ID",
        )
        == "http://fixture-user-region-ID-sid-demo-t-5:fixture-pass@proxy.example.test:443"
    )
    assert (
        app.proxy_for_region(
            "http://bunnyVgvhjyJ9-country-KR-session-976056793-sessTime-5:98963225@proxy.us.bunnyproxy.com:18080",
            "ID",
        )
        == "http://bunnyVgvhjyJ9-country-ID-session-976056793-sessTime-5:98963225@proxy.us.bunnyproxy.com:18080"
    )
    assert (
        app.proxy_for_region(
            "http://7774239-9c7d895c63:e607530e89-US-41966127-5m@gate.kookeey.info:1000",
            "TR",
        )
        == "http://7774239-9c7d895c63:e607530e89-TR-41966127-5m@gate.kookeey.info:1000"
    )


def test_proxy_config_view_exposes_stage_pools_without_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_INDIA_PROMOTION_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_INDIA_PROMOTION_PROXY_POOL", f"{FIXTURE_PROXY};{FIXTURE_PROXY_TWO}")

    view = app.proxy_config_view("upi")
    serialized = json.dumps(view)
    stages = {item["stage"]: item for item in view["stages"]}

    assert tuple(stages) == app.PROXY_STAGE_ORDER
    assert stages["checkout"]["region"] == "IN"
    assert stages["promotion"]["region"] == "VN"
    assert stages["provider"]["fallback"]["env_key"] == "OPENAI_PAY_INDIA_PROXY"
    assert stages["promotion"]["fallback"]["env_key"] == "OPENAI_PAY_INDIA_PROMOTION_PROXY"
    assert stages["promotion"]["pool"]["env_key"] == "OPENAI_PAY_INDIA_PROMOTION_PROXY_POOL"
    assert stages["promotion"]["pool"]["count"] == 2
    assert [item["stage"] for item in view["visible_stages"]] == ["checkout", "promotion", "provider"]
    assert "fixture-user" not in serialized
    assert "proxy.example.test" not in serialized


def test_stage_proxy_update_writes_stage_specific_env_keys(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("UNRELATED_VALUE=keep\n", encoding="utf-8")
    monkeypatch.setattr(app, "PAYLINK_ENV_PATH", env_path)
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("OPENAI_PAY_SWISS_PROMOTION_PROXY", "")
    monkeypatch.setenv("OPENAI_PAY_SWISS_PROMOTION_PROXY_POOL", "")

    result = app.update_provider_proxy_config(
        app.ProviderProxyUpdateRequest(
            provider="twint",
            stage="promotion",
            fallbackProxy=FIXTURE_PROXY,
            proxyPool=FIXTURE_PROXY_TWO,
        )
    )

    content = env_path.read_text(encoding="utf-8")
    promotion_stage = {item["stage"]: item for item in result["config"]["stages"]}["promotion"]
    assert "UNRELATED_VALUE=keep" in content
    assert f'OPENAI_PAY_SWISS_PROMOTION_PROXY="{FIXTURE_PROXY}"' in content
    assert f'OPENAI_PAY_SWISS_PROMOTION_PROXY_POOL="{FIXTURE_PROXY_TWO}"' in content
    assert promotion_stage["fallback"]["env_key"] == "OPENAI_PAY_SWISS_PROMOTION_PROXY"
    assert promotion_stage["pool"]["count"] == 1
    assert "fixture-user" not in json.dumps(result)


def test_checkout_stage_pool_overrides_provider_pool(monkeypatch):
    checkout_proxy = "http://fixture-checkout:fixture-pass@checkout-proxy.example.test:443"
    provider_proxy = "http://fixture-provider:fixture-pass@provider-proxy.example.test:443"
    monkeypatch.setenv("OPENAI_PAY_IDEAL_CHECKOUT_PROXY_POOL", checkout_proxy)
    monkeypatch.setenv("OPENAI_PAY_IDEAL_CHECKOUT_PROXY", "")
    monkeypatch.setattr(app, "IDEAL_PROXY_POOL", [provider_proxy])
    monkeypatch.setattr(app, "IDEAL_STAGE_PROXY", provider_proxy)

    candidates = app.proxy_candidates_for_link_type("", "ideal")

    assert candidates == [checkout_proxy]


def test_approve_stage_uses_override_then_provider_fallback(monkeypatch):
    approve_proxy = "http://fixture-approve:fixture-pass@approve-proxy.example.test:443"
    provider_proxy = "http://fixture-provider:fixture-pass@provider-proxy.example.test:443"
    req = app.LongLinkRequest(link_type="gcash", billing_country="PH", payment_locale="en-PH")
    monkeypatch.setenv("OPENAI_PAY_PH_APPROVE_PROXY", approve_proxy)
    monkeypatch.setenv("OPENAI_PAY_PH_APPROVE_PROXY_POOL", "")
    monkeypatch.setattr(app, "PH_PROXY_POOL", [])
    monkeypatch.setattr(app, "PH_STAGE_PROXY", provider_proxy)
    monkeypatch.setattr(app, "PROVIDER_PROXY_POOL", [])
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "DEFAULT_PROXY", "")

    assert app.approve_stage_proxy(req, fallback_proxy=provider_proxy) == approve_proxy

    monkeypatch.setenv("OPENAI_PAY_PH_APPROVE_PROXY", "")

    assert app.approve_stage_proxy(req, fallback_proxy=provider_proxy) == provider_proxy
