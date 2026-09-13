# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock

from config import env_loader
from core.ant_browser_client import AntBrowserClient, AntBrowserError, AntBrowserOpenResult
from webui import config_editor


def response(status_code, payload):
    item = Mock()
    item.status_code = status_code
    item.ok = 200 <= status_code < 300
    item.json.return_value = payload
    return item


class AntBrowserClientTests(unittest.TestCase):
    def build_client(self, **overrides):
        values = {
            "api_base": "http://127.0.0.1:19876",
            "api_key": "secret-key",
            "profile_id": "profile-123",
            "profile_mode": "existing",
            "timeout": 12,
        }
        values.update(overrides)
        return AntBrowserClient(**values)

    def test_config_registry_exposes_secret_and_fields(self):
        fields = {item["key"]: item for item in config_editor.EDITABLE_FIELDS}
        self.assertIn("ANT_BROWSER_API_KEY", env_loader.SECRET_ENV_KEYS)
        self.assertTrue(fields["ANT_BROWSER_API_KEY"].get("secret"))
        self.assertEqual(fields["ANT_BROWSER_API_KEY"].get("storage"), "env")
        self.assertIn("ANT_BROWSER_PROFILE_MODE", fields)
        self.assertIn("ANT_BROWSER_PROFILE_ID", fields)
        self.assertIn("ANT_BROWSER_KEEP_BROWSER_OPEN", fields)
        self.assertIn("ANT_BROWSER_DELETE_MANAGED_PROFILE", fields)

    def test_reuses_running_profile_without_launching(self):
        client = self.build_client()
        client.http.request = Mock(return_value=response(200, {
            "ok": True,
            "profileId": "profile-123",
            "profileName": "Primary",
            "running": True,
            "debugReady": True,
            "directDebugUrl": "http://127.0.0.1:9222",
        }))

        opened = client.open_profile()

        self.assertFalse(opened.started_by_run)
        self.assertEqual(opened.debugger_address, "127.0.0.1:9222")
        self.assertEqual(client.http.request.call_count, 1)
        self.assertEqual(client.http.request.call_args.args[:2], ("GET", "http://127.0.0.1:19876/api/profiles/profile-123/status"))

    def test_starts_stopped_profile_without_start_urls_and_uses_debug_port(self):
        client = self.build_client()
        client.http.request = Mock(side_effect=[
            response(200, {"ok": True, "profileId": "profile-123", "running": False, "debugReady": False}),
            response(200, {
                "ok": True,
                "profileId": "profile-123",
                "profileName": "Primary",
                "debugReady": True,
                "debugPort": 9233,
            }),
        ])

        opened = client.open_profile()

        self.assertTrue(opened.started_by_run)
        self.assertEqual(opened.cdp_url, "http://127.0.0.1:9233")
        method, url = client.http.request.call_args.args[:2]
        self.assertEqual((method, url), ("POST", "http://127.0.0.1:19876/api/launch"))
        self.assertEqual(client.http.request.call_args.kwargs["json"], {
            "profileId": "profile-123",
        })

    def test_api_key_header_is_configurable(self):
        client = self.build_client(api_key_header="X-Custom-Ant-Key")
        self.assertEqual(client.http.headers["X-Custom-Ant-Key"], "secret-key")
        self.assertNotIn("X-Ant-Api-Key", client.http.headers)

    def test_invalid_or_remote_cdp_endpoint_is_rejected(self):
        with self.assertRaises(AntBrowserError):
            AntBrowserClient._debugger_address("http://192.0.2.10:9222")
        with self.assertRaises(AntBrowserError):
            AntBrowserClient._debugger_address("not-a-url")

    def test_api_error_redacts_api_key(self):
        client = self.build_client()
        client.http.request = Mock(return_value=response(401, {
            "ok": False,
            "error": "unauthorized secret-key",
        }))

        with self.assertRaises(AntBrowserError) as caught:
            client.get_profile_status()

        self.assertNotIn("secret-key", str(caught.exception))
        self.assertIn("***", str(caught.exception))

    def test_cleanup_stops_only_profiles_started_by_this_run(self):
        client = self.build_client()
        client.stop_profile = Mock()
        opened_by_run = AntBrowserOpenResult(
            profile_id="profile-123",
            profile_name="Primary",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=True,
            created_by_run=False,
            raw={},
        )
        reused = AntBrowserOpenResult(
            profile_id="profile-123",
            profile_name="Primary",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=False,
            created_by_run=False,
            raw={},
        )

        client.cleanup_profile(reused)
        client.stop_profile.assert_not_called()
        client.cleanup_profile(opened_by_run)
        client.stop_profile.assert_called_once_with("profile-123")

    def test_managed_profile_is_created_with_task_proxy_then_started(self):
        client = self.build_client(profile_id="", profile_mode="managed")
        proxy = "http://user:password@proxy.example.test:8080"
        client.http.request = Mock(side_effect=[
            response(201, {
                "ok": True,
                "profileId": "managed-123",
                "profileName": "gpt-registrar-123",
            }),
            response(200, {
                "ok": True,
                "profileId": "managed-123",
                "profileName": "gpt-registrar-123",
                "debugReady": True,
                "directDebugUrl": "http://127.0.0.1:9223",
            }),
        ])

        opened = client.open_profile(proxy=proxy)

        self.assertTrue(opened.created_by_run)
        self.assertTrue(opened.started_by_run)
        self.assertEqual(opened.profile_id, "managed-123")
        create_call, launch_call = client.http.request.call_args_list
        self.assertEqual(create_call.args[:2], ("POST", "http://127.0.0.1:19876/api/profiles"))
        profile = create_call.kwargs["json"]["profile"]
        self.assertTrue(profile["profileName"].startswith("gpt-registrar-"))
        self.assertNotIn("@", profile["profileName"])
        self.assertEqual(profile["tags"], ["gpt-registrar", "managed"])
        self.assertEqual(profile["proxyConfig"], proxy)
        self.assertNotIn("proxyId", profile)
        self.assertEqual(launch_call.args[:2], ("POST", "http://127.0.0.1:19876/api/launch"))
        self.assertEqual(launch_call.kwargs["json"], {
            "profileId": "managed-123",
        })

    def test_managed_profile_uses_explicit_direct_proxy_without_task_proxy(self):
        client = self.build_client(profile_id="", profile_mode="managed")
        client.http.request = Mock(side_effect=[
            response(201, {"ok": True, "profileId": "managed-123"}),
            response(200, {
                "ok": True,
                "profileId": "managed-123",
                "debugReady": True,
                "debugPort": 9223,
            }),
        ])

        client.open_profile()

        profile = client.http.request.call_args_list[0].kwargs["json"]["profile"]
        self.assertEqual(profile["proxyId"], "__direct__")
        self.assertEqual(profile["proxyConfig"], "direct://")

    def test_managed_cleanup_stops_then_deletes_profile(self):
        client = self.build_client(profile_id="", profile_mode="managed")
        calls = []
        client.stop_profile = Mock(side_effect=lambda profile_id: calls.append(("stop", profile_id)))
        client.delete_profile = Mock(side_effect=lambda profile_id: calls.append(("delete", profile_id)))
        opened = AntBrowserOpenResult(
            profile_id="managed-123",
            profile_name="gpt-registrar-123",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=True,
            created_by_run=True,
            raw={},
        )

        client.cleanup_profile(opened)

        self.assertEqual(calls, [("stop", "managed-123"), ("delete", "managed-123")])

    def test_managed_cleanup_keeps_profile_when_requested(self):
        client = self.build_client(profile_id="", profile_mode="managed", keep_browser_open=True)
        client.stop_profile = Mock()
        client.delete_profile = Mock()
        opened = AntBrowserOpenResult(
            profile_id="managed-123",
            profile_name="gpt-registrar-123",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=True,
            created_by_run=True,
            raw={},
        )

        client.cleanup_profile(opened)

        client.stop_profile.assert_not_called()
        client.delete_profile.assert_not_called()

    def test_managed_cleanup_can_preserve_profile_after_stopping(self):
        client = self.build_client(
            profile_id="",
            profile_mode="managed",
            delete_managed_profile=False,
        )
        client.stop_profile = Mock()
        client.delete_profile = Mock()
        opened = AntBrowserOpenResult(
            profile_id="managed-123",
            profile_name="gpt-registrar-123",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=True,
            created_by_run=True,
            raw={},
        )

        client.cleanup_profile(opened)

        client.stop_profile.assert_called_once_with("managed-123")
        client.delete_profile.assert_not_called()

    def test_existing_profile_cleanup_never_deletes_profile(self):
        client = self.build_client()
        client.stop_profile = Mock()
        client.delete_profile = Mock()
        opened = AntBrowserOpenResult(
            profile_id="profile-123",
            profile_name="Primary",
            cdp_url="http://127.0.0.1:9222",
            debugger_address="127.0.0.1:9222",
            started_by_run=True,
            created_by_run=False,
            raw={},
        )

        client.cleanup_profile(opened)

        client.stop_profile.assert_called_once_with("profile-123")
        client.delete_profile.assert_not_called()

    def test_managed_launch_failure_cleans_up_created_profile(self):
        client = self.build_client(profile_id="", profile_mode="managed")
        client.http.request = Mock(side_effect=[
            response(201, {"ok": True, "profileId": "managed-123"}),
            response(500, {"ok": False, "error": "launch failed"}),
            response(200, {"ok": True, "stopped": True}),
            response(200, {"ok": True, "deleted": True}),
        ])

        with self.assertRaises(AntBrowserError):
            client.open_profile()

        requests = [(call.args[0], call.args[1]) for call in client.http.request.call_args_list]
        self.assertEqual(requests, [
            ("POST", "http://127.0.0.1:19876/api/profiles"),
            ("POST", "http://127.0.0.1:19876/api/launch"),
            ("POST", "http://127.0.0.1:19876/api/profiles/managed-123/stop"),
            ("DELETE", "http://127.0.0.1:19876/api/profiles/managed-123"),
        ])

    def test_managed_create_error_redacts_api_key(self):
        client = self.build_client(profile_id="", profile_mode="managed")
        client.http.request = Mock(return_value=response(400, {
            "ok": False,
            "error": "invalid secret-key",
        }))

        with self.assertRaises(AntBrowserError) as caught:
            client.open_profile(proxy="http://user:password@proxy.example.test:8080")

        self.assertNotIn("secret-key", str(caught.exception))
        self.assertIn("***", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
