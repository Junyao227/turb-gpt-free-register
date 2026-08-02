# -*- coding: utf-8 -*-
"""SMSBower metadata client used by the WebUI configuration screen."""
from __future__ import annotations

from typing import Any

import requests


DEFAULT_BASE_URL = "https://smsbower.page/stubs/handler_api.php"


class SmsBowerClient:
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, timeout: int = 20, session=None):
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        self.timeout = max(1, int(timeout or 20))
        self.session = session or requests.Session()

    def _get_text(self, action: str, **params: str) -> str:
        if not self.api_key:
            raise ValueError("请先填写 SMSBower API Key")
        query = {"api_key": self.api_key, "action": action}
        query.update({key: value for key, value in params.items() if str(value or "").strip()})
        response = self.session.get(self.base_url, params=query, timeout=self.timeout)
        text = str(getattr(response, "text", "") or "").strip()
        if not getattr(response, "ok", 200 <= int(getattr(response, "status_code", 0) or 0) < 300):
            raise RuntimeError(text or f"SMSBower {action} HTTP {getattr(response, 'status_code', '')}")
        if text in {"BAD_KEY", "BAD_ACTION"}:
            raise RuntimeError(f"SMSBower 返回 {text}")
        return text

    def _get_json(self, action: str, **params: str) -> Any:
        text = self._get_text(action, **params)
        try:
            import json

            return json.loads(text)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"SMSBower {action} 返回格式异常: {text[:160]}") from exc

    def get_balance(self) -> float:
        text = self._get_text("getBalance")
        if not text.startswith("ACCESS_BALANCE:"):
            raise RuntimeError(f"SMSBower getBalance 返回异常: {text[:160]}")
        try:
            return float(text.split(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(f"SMSBower getBalance 返回异常: {text[:160]}") from exc

    def get_countries(self) -> list[dict]:
        payload = self._get_json("getCountries")
        if isinstance(payload, dict):
            raw_items = payload.get("countries") or payload.get("data") or payload.get("items") or payload
        else:
            raw_items = payload

        if isinstance(raw_items, dict):
            entries = list(raw_items.items())
        elif isinstance(raw_items, list):
            entries = [("", item) for item in raw_items]
        else:
            entries = []

        countries = []
        for fallback_id, item in entries:
            if not isinstance(item, dict):
                continue
            country_id = str(item.get("id") or item.get("country") or fallback_id or "").strip()
            name = str(item.get("eng") or item.get("name") or item.get("title") or item.get("chn") or country_id).strip()
            if country_id:
                countries.append({"id": country_id, "name": name or country_id})
        countries.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        return countries

    def get_services(self, *, country: str = "") -> list[dict]:
        payload = self._get_json("getServicesList", country=country, lang="en")
        if isinstance(payload, dict):
            raw_items = payload.get("services") or payload.get("data") or payload.get("items") or []
        else:
            raw_items = payload

        if isinstance(raw_items, dict):
            entries = list(raw_items.items())
        elif isinstance(raw_items, list):
            entries = [("", item) for item in raw_items]
        else:
            entries = []

        services = []
        for fallback_code, item in entries:
            if isinstance(item, str):
                code = str(fallback_code or item).strip()
                name = item.strip()
            elif isinstance(item, dict):
                code = str(item.get("code") or item.get("service") or item.get("id") or fallback_code or "").strip()
                name = str(item.get("name") or item.get("title") or item.get("eng") or code).strip()
            else:
                continue
            if code:
                services.append({"code": code, "name": name or code})
        services.sort(key=lambda item: (item["name"].casefold(), item["code"]))
        return services

    def get_price_summary(self, *, country: str, service: str) -> dict:
        country = str(country or "").strip()
        service = str(service or "").strip()
        if not country or not service:
            return {"country": country, "service": service, "count": 0, "provider_count": 0, "prices": []}

        payload = self._get_json("getPricesV3", country=country, service=service)
        provider_map = {}
        if isinstance(payload, dict):
            country_payload = payload.get(country)
            if isinstance(country_payload, dict):
                service_payload = country_payload.get(service)
                if isinstance(service_payload, dict):
                    provider_map = service_payload

        tiers = []
        for fallback_id, item in provider_map.items():
            if not isinstance(item, dict):
                continue
            try:
                price = float(item.get("price", item.get("cost")))
                count = max(0, int(float(item.get("count", item.get("stock", 0)) or 0)))
            except (TypeError, ValueError):
                continue
            provider_id = str(item.get("provider_id") or item.get("providerId") or fallback_id or "").strip()
            if provider_id and count > 0:
                tiers.append({"provider_id": provider_id, "price": price, "count": count})
        tiers.sort(key=lambda item: (item["price"], -item["count"], item["provider_id"]))
        prices = sorted({item["price"] for item in tiers})
        return {
            "country": country,
            "service": service,
            "count": sum(item["count"] for item in tiers),
            "provider_count": len(tiers),
            "min_price": prices[0] if prices else None,
            "max_price": prices[-1] if prices else None,
            "prices": prices,
            "tiers": tiers,
        }
