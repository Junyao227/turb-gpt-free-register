import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


FIXTURE_PROXY = "http://fixture-user:fixture-pass@proxy.example.test:443"
FIXTURE_PROXY_TWO = "http://fixture-user-two:fixture-pass-two@proxy-two.example.test:8443"


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


def test_proxy_config_view_maps_paypal_to_its_dedicated_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_PROXY", FIXTURE_PROXY)
    monkeypatch.setenv("OPENAI_PAY_PAYPAL_PROXY_POOL", FIXTURE_PROXY_TWO)

    view = app.proxy_config_view("paypal")
    serialized = json.dumps(view)

    assert view["fallback"]["env_key"] == "OPENAI_PAY_PAYPAL_PROXY"
    assert view["pool"]["env_key"] == "OPENAI_PAY_PAYPAL_PROXY_POOL"
    assert view["pool"]["count"] == 1
    assert "fixture-user" not in serialized
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


def test_provider_proxy_runtime_mapping_covers_swiss_and_gopay_settings():
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_SWISS_PROXY"] == "SWISS_STAGE_PROXY"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_SWISS_PROXY_POOL"] == "SWISS_PROXY_POOL"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GOPAY_PROVIDER_PROXY"] == "GOPAY_PROVIDER_STAGE_PROXY"
    assert app.PROXY_ENV_RUNTIME_NAMES["OPENAI_PAY_GOPAY_PROVIDER_PROXY_POOL"] == "GOPAY_PROVIDER_PROXY_POOL"


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


def test_dedicated_paypal_proxy_pool_has_precedence_over_generic_checkout_candidates(monkeypatch):
    paypal_proxy = "http://fixture-paypal:fixture-pass@paypal-proxy.example.test:443"
    generic_proxy = "http://fixture-generic:fixture-pass@generic-proxy.example.test:443"
    monkeypatch.setattr(app, "PAYPAL_PROXY_POOL", [paypal_proxy])
    monkeypatch.setattr(app, "PAYPAL_STAGE_PROXY", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [generic_proxy])
    monkeypatch.setattr(app, "DEFAULT_PROXY", generic_proxy)

    candidates = app.proxy_candidates_for_link_type("", "paypal")

    assert candidates[0] == paypal_proxy
    assert generic_proxy in candidates[1:]
