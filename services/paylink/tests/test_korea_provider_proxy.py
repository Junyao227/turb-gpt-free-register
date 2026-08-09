from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def test_provider_stage_proxy_rewrites_provider_pool_to_korea(monkeypatch):
    monkeypatch.setattr(app, "KOREA_PROXY_POOL", [])
    monkeypatch.setattr(
        app,
        "PROVIDER_PROXY_POOL",
        ["http://fixture-user-region-JP-sid-demo-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "KOREA_STAGE_PROXY", "")
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY",
        "http://fixture-user-region-JP-sid-fallback-t-5:fixture-pass@proxy.example.test:443",
    )
    monkeypatch.setitem(app._proxy_cursor, "korea", 0)

    proxy = app.provider_stage_proxy(app.LongLinkRequest(link_type="korea"))

    assert "region-KR" in proxy
    assert "region-JP" not in proxy


def test_provider_stage_proxy_prefers_explicit_proxy():
    proxy = app.provider_stage_proxy(
        app.LongLinkRequest(
            link_type="korea",
            proxy="http://user:pass@custom-proxy.example:8443",
        )
    )

    assert proxy == "http://user:pass@custom-proxy.example:8443"


def test_pix_provider_stage_proxy_rewrites_explicit_proxy_to_brazil():
    proxy = app.provider_stage_proxy(
        app.LongLinkRequest(
            link_type="pix",
            proxy="http://user-region-US-sid-demo-t-5:pass@proxy.example:3010",
        )
    )

    assert "region-BR" in proxy
    assert "region-US" not in proxy


def test_pix_checkout_proxy_candidates_rewrite_explicit_proxy_to_brazil():
    proxies = app.proxy_candidates_for_link_type(
        "http://user-region-US-sid-demo-t-5:pass@proxy.example:3010",
        "pix",
    )

    assert proxies == ["http://user-region-BR-sid-demo-t-5:pass@proxy.example:3010"]


def test_pix_promotion_proxy_rewrites_brazil_seed_to_vietnam(monkeypatch):
    monkeypatch.setattr(app, "PIX_PROMOTION_PROXY_POOL", [])
    monkeypatch.setattr(app, "PIX_PROMOTION_STAGE_PROXY", "")
    proxy = app.pix_promotion_proxy(
        "http://user-region-BR-sid-demo-t-5:pass@proxy.example:3010"
    )

    assert "region-VN" in proxy
    assert "region-BR" not in proxy


def test_pix_promotion_proxy_prefers_dedicated_vietnam_pool(monkeypatch):
    vietnam_proxy = "http://fixture-user:fixture-pass-VN-session@proxy.example.test:443"
    monkeypatch.setattr(app, "PIX_PROMOTION_PROXY_POOL", [vietnam_proxy])
    monkeypatch.setattr(app, "PIX_PROMOTION_STAGE_PROXY", "")
    monkeypatch.setitem(app._proxy_cursor, "pix_promotion", 0)

    proxy = app.pix_promotion_proxy(
        "http://fixture-user:fixture-pass-BR-session@proxy.example.test:443"
    )

    assert proxy == vietnam_proxy


def test_provider_stage_proxy_rewrites_provider_pool_to_india(monkeypatch):
    monkeypatch.setattr(app, "INDIA_PROXY_POOL", [])
    monkeypatch.setattr(
        app,
        "PROVIDER_PROXY_POOL",
        ["http://fixture-user-region-JP-sid-demo-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "INDIA_STAGE_PROXY", "")
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY",
        "http://fixture-user-region-JP-sid-fallback-t-5:fixture-pass@proxy.example.test:443",
    )
    monkeypatch.setitem(app._proxy_cursor, "upi", 0)

    proxy = app.provider_stage_proxy(app.LongLinkRequest(link_type="upi"))

    assert "region-IN" in proxy
    assert "region-JP" not in proxy


def test_upi_checkout_proxy_candidates_use_india_pool(monkeypatch):
    monkeypatch.setattr(
        app,
        "INDIA_PROXY_POOL",
        ["http://fixture-user-region-IN-sid-demo-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(app, "INDIA_STAGE_PROXY", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY",
        "http://fixture-user-region-JP-sid-fallback-t-5:fixture-pass@proxy.example.test:443",
    )

    proxies = app.proxy_candidates_for_link_type("", "upi")

    assert proxies
    assert all("region-IN" in proxy for proxy in proxies)
    assert all("region-JP" not in proxy for proxy in proxies)


def test_korea_and_ideal_checkout_candidates_use_target_regions(monkeypatch):
    korea_proxy = "http://fixture-user-region-KR-sid-demo-t-5:fixture-pass@proxy.example.test:443"
    ideal_proxy = "http://fixture-user-region-NL-sid-demo-t-5:fixture-pass@proxy.example.test:443"
    monkeypatch.setattr(app, "KOREA_PROXY_POOL", [korea_proxy])
    monkeypatch.setattr(app, "KOREA_STAGE_PROXY", "")
    monkeypatch.setattr(app, "IDEAL_PROXY_POOL", [])
    monkeypatch.setattr(app, "IDEAL_STAGE_PROXY", "")
    monkeypatch.setattr(app, "PROVIDER_PROXY_POOL", [ideal_proxy])
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "DEFAULT_PROXY", "")

    assert app.proxy_candidates_for_link_type("", "korea") == [korea_proxy]
    assert app.proxy_candidates_for_link_type("", "ideal") == [ideal_proxy]


def test_checkout_retries_network_proxy_error(monkeypatch):
    attempts = []

    class Session:
        proxies = {}

    monkeypatch.setattr(app, "proxy_candidates_for_link_type", lambda *_args: ["http://proxy-1", "http://proxy-2"])
    monkeypatch.setattr(app, "build_chatgpt_session", lambda _req: Session())
    monkeypatch.setattr(app, "log_event", lambda *_args, **_kwargs: None)

    def create_checkout(_req, _session):
        attempts.append(dict(_session.proxies))
        if len(attempts) == 1:
            raise requests.exceptions.ProxyError("fixture proxy failed")
        return {"cs_id": "cs_fixture"}

    monkeypatch.setattr(app, "create_checkout", create_checkout)

    checkout, _session = app.create_checkout_with_proxy_retry(app.LongLinkRequest(link_type="upi"))

    assert checkout == {"cs_id": "cs_fixture"}
    assert len(attempts) == 2


def test_provider_stage_proxy_prefers_japan_pool_for_gopay(monkeypatch):
    monkeypatch.setattr(
        app,
        "GOPAY_PROVIDER_PROXY_POOL",
        ["http://fixture-user-region-JP-sid-demo-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(app, "DEFAULT_PROXY_POOL", [])
    monkeypatch.setattr(app, "GOPAY_PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY",
        "http://fixture-user-region-JP-sid-fallback-t-5:fixture-pass@proxy.example.test:443",
    )
    monkeypatch.setitem(app._proxy_cursor, "gopay", 0)

    proxy = app.provider_stage_proxy(app.LongLinkRequest(link_type="gopay"))

    assert "region-JP" in proxy


def test_gcash_checkout_and_provider_stages_prefer_dedicated_ph_pool(monkeypatch):
    ph_proxy = "http://fixture-user-region-PH-sid-demo-t-5:fixture-pass@proxy.example.test:443"
    monkeypatch.setattr(
        app,
        "PH_PROXY_POOL",
        [ph_proxy],
    )
    monkeypatch.setattr(app, "PH_STAGE_PROXY", "")
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY_POOL",
        ["http://fixture-user-region-JP-sid-default-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(
        app,
        "PROVIDER_PROXY_POOL",
        ["http://fixture-user-region-JP-sid-provider-t-5:fixture-pass@proxy.example.test:443"],
    )
    monkeypatch.setattr(app, "PROVIDER_STAGE_PROXY", "")
    monkeypatch.setattr(
        app,
        "DEFAULT_PROXY",
        "http://fixture-user-region-JP-sid-fallback-t-5:fixture-pass@proxy.example.test:443",
    )
    monkeypatch.setitem(app._proxy_cursor, "gcash", 0)

    checkout_candidates = app.proxy_candidates_for_link_type("", "gcash")
    proxy = app.provider_stage_proxy(app.LongLinkRequest(link_type="gcash"))

    assert checkout_candidates[0] == ph_proxy
    assert all("region-PH" in candidate for candidate in checkout_candidates)
    assert all("region-JP" not in candidate for candidate in checkout_candidates)
    assert "region-PH" in proxy
    assert "region-JP" not in proxy
