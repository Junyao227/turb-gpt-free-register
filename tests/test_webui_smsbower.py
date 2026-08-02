# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from webui.app import create_app


class SmsBowerWebUiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app(auth_code="test-auth").test_client()
        self.client.environ_base["HTTP_X_AUTH_CODE"] = "test-auth"

    @patch("core.smsbower_client.SmsBowerClient.get_balance", return_value=8.25)
    def test_balance_endpoint(self, get_balance):
        response = self.client.post("/api/smsbower/balance", json={
            "api_key": "secret", "base_url": "https://smsbower.example/handler_api.php"
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["balance"], 8.25)
        get_balance.assert_called_once_with()

    @patch("core.smsbower_client.SmsBowerClient.get_countries", return_value=[{"id": "151", "name": "Chile"}])
    def test_countries_endpoint(self, get_countries):
        response = self.client.post("/api/smsbower/countries", json={"api_key": "secret"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["countries"][0]["id"], "151")
        get_countries.assert_called_once_with()

    @patch("core.smsbower_client.SmsBowerClient.get_services", return_value=[{"code": "dr", "name": "OpenAI"}])
    def test_services_endpoint_passes_country(self, get_services):
        response = self.client.post("/api/smsbower/services", json={"api_key": "secret", "country": "151"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["services"][0]["code"], "dr")
        get_services.assert_called_once_with(country="151")

    @patch("core.smsbower_client.SmsBowerClient.get_price_summary", return_value={
        "country": "151", "service": "dr", "count": 10, "provider_count": 2,
        "min_price": 0.04, "max_price": 0.07, "prices": [0.04, 0.07], "tiers": [],
    })
    def test_prices_endpoint_passes_selection(self, get_price_summary):
        response = self.client.post("/api/smsbower/prices", json={
            "api_key": "secret", "country": "151", "service": "dr"
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 10)
        get_price_summary.assert_called_once_with(country="151", service="dr")


if __name__ == "__main__":
    unittest.main()
