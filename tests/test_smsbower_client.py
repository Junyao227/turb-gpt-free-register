# -*- coding: utf-8 -*-
import json
import unittest

from core.smsbower_client import SmsBowerClient


class _Response:
    ok = True
    status_code = 200

    def __init__(self, payload):
        self.text = payload if isinstance(payload, str) else json.dumps(payload)


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return _Response(self.responses.pop(0))


class SmsBowerClientTests(unittest.TestCase):
    def test_normalizes_countries_and_services(self):
        session = _Session([
            {"151": {"id": "151", "eng": "Chile"}, "187": {"id": "187", "eng": "United States"}},
            {"status": "success", "services": [{"code": "dr", "name": "OpenAI"}]},
        ])
        client = SmsBowerClient("secret", session=session)

        self.assertEqual(client.get_countries()[0], {"id": "151", "name": "Chile"})
        self.assertEqual(client.get_services(country="151"), [{"code": "dr", "name": "OpenAI"}])
        self.assertEqual(session.calls[1]["params"]["country"], "151")

    def test_aggregates_live_price_tiers(self):
        session = _Session([{
            "151": {"dr": {
                "a": {"provider_id": 10, "price": 0.07, "count": 2},
                "b": {"provider_id": 11, "price": 0.04, "count": 5},
                "empty": {"provider_id": 12, "price": 0.01, "count": 0},
            }}
        }])
        client = SmsBowerClient("secret", session=session)

        result = client.get_price_summary(country="151", service="dr")

        self.assertEqual(result["count"], 7)
        self.assertEqual(result["provider_count"], 2)
        self.assertEqual(result["prices"], [0.04, 0.07])
        self.assertEqual(result["min_price"], 0.04)

    def test_balance_uses_query_only_action(self):
        session = _Session(["ACCESS_BALANCE:12.5"])
        client = SmsBowerClient("secret", session=session)

        self.assertEqual(client.get_balance(), 12.5)
        self.assertEqual(session.calls[0]["params"]["action"], "getBalance")


if __name__ == "__main__":
    unittest.main()
