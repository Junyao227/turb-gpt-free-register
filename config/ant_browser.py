# -*- coding: utf-8 -*-
"""Ant Browser local Launch API configuration."""
from config.env_loader import apply_env_overrides, env_str


ANT_BROWSER_API_BASE: str = "http://127.0.0.1:19876"
ANT_BROWSER_API_KEY: str = env_str("ANT_BROWSER_API_KEY", "")
ANT_BROWSER_API_KEY_HEADER: str = "X-Ant-Api-Key"

# ``managed`` creates a disposable profile for each registration task. ``existing``
# attaches to the configured profile ID for backwards compatibility.
ANT_BROWSER_PROFILE_MODE: str = "managed"
ANT_BROWSER_PROFILE_ID: str = ""
ANT_BROWSER_START_TIMEOUT: int = 90
ANT_BROWSER_KEEP_BROWSER_OPEN: bool = False
ANT_BROWSER_DELETE_MANAGED_PROFILE: bool = True
ANT_BROWSER_START_URL: str = "https://chatgpt.com/auth/login"


apply_env_overrides(globals(), {
    "ANT_BROWSER_API_BASE": "str",
    "ANT_BROWSER_API_KEY": "str",
    "ANT_BROWSER_API_KEY_HEADER": "str",
    "ANT_BROWSER_PROFILE_MODE": "str",
    "ANT_BROWSER_PROFILE_ID": "str",
    "ANT_BROWSER_START_TIMEOUT": "int",
    "ANT_BROWSER_KEEP_BROWSER_OPEN": "bool",
    "ANT_BROWSER_DELETE_MANAGED_PROFILE": "bool",
    "ANT_BROWSER_START_URL": "str",
})
