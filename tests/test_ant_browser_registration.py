# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch

import main
from config import roxybrowser as registration_config
from core.ant_browser_registration import run_ant_browser_registration


class AntBrowserRegistrationDispatchTests(unittest.TestCase):
    @patch("core.ant_browser_registration.run_ant_browser_registration")
    def test_main_dispatches_ant_browser_driver(self, run_ant_browser_registration):
        run_ant_browser_registration.return_value = {"success": True, "email": "person@example.test"}
        old_driver = registration_config.REGISTRATION_DRIVER
        registration_config.REGISTRATION_DRIVER = "ant_browser"
        try:
            result = main.run_registration(
                email="person@example.test",
                name="Person",
                birthday="1990-01-01",
                proxy="http://proxy.example.test:8080",
            )
        finally:
            registration_config.REGISTRATION_DRIVER = old_driver

        self.assertTrue(result["success"])
        run_ant_browser_registration.assert_called_once()
        self.assertEqual(run_ant_browser_registration.call_args.kwargs["email"], "person@example.test")
        self.assertEqual(
            run_ant_browser_registration.call_args.kwargs["proxy"],
            "http://proxy.example.test:8080",
        )


class AntBrowserRegistrationProxyTests(unittest.TestCase):
    @patch("core.email_provider.release_email")
    @patch("core.ant_browser_registration.AntBrowserClient")
    @patch("core.ant_browser_registration.pick_proxy")
    def test_uses_one_proxy_pool_entry_when_task_proxy_is_not_provided(
        self,
        pick_proxy,
        client_class,
        _release_email,
    ):
        selected_proxy = "http://user:password@proxy.example.test:8080"
        pick_proxy.return_value = selected_proxy
        client = client_class.return_value
        client.open_profile.return_value = Mock()
        client.build_driver.side_effect = RuntimeError("test driver setup failure")

        result = run_ant_browser_registration(
            email="person@example.test",
            name="Person",
            birthday="1990-01-01",
        )

        self.assertFalse(result["success"])
        pick_proxy.assert_called_once_with()
        client.open_profile.assert_called_once_with(proxy=selected_proxy)

    @patch("core.email_provider.release_email")
    @patch("core.ant_browser_registration.AntBrowserClient")
    @patch("core.ant_browser_registration.pick_proxy")
    def test_preserves_explicit_task_proxy(
        self,
        pick_proxy,
        client_class,
        _release_email,
    ):
        supplied_proxy = "socks5h://user:password@proxy.example.test:1080"
        client = client_class.return_value
        client.open_profile.return_value = Mock()
        client.build_driver.side_effect = RuntimeError("test driver setup failure")

        result = run_ant_browser_registration(
            email="person@example.test",
            name="Person",
            birthday="1990-01-01",
            proxy=supplied_proxy,
        )

        self.assertFalse(result["success"])
        pick_proxy.assert_not_called()
        client.open_profile.assert_called_once_with(proxy=supplied_proxy)


if __name__ == "__main__":
    unittest.main()
