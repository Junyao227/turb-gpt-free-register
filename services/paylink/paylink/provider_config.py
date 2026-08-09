from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "providers.ini"


class ProviderConfigError(ValueError):
    """Raised when a provider is disabled or its non-secret configuration is invalid."""


@dataclass(frozen=True)
class ProviderSettings:
    enabled: bool
    country: str
    locale: str


def _parse_enabled(value: str, section: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigError(f"{section}.enabled must be true or false")


def load_provider_settings(section: str, path: Path | None = None) -> ProviderSettings:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise ProviderConfigError(f"provider configuration file is missing: {config_path}")

    parser = ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section(section):
        raise ProviderConfigError(f"provider configuration section is missing: [{section}]")

    values = parser[section]
    missing = [key for key in ("enabled", "country", "locale") if not str(values.get(key) or "").strip()]
    if missing:
        raise ProviderConfigError(f"{section} is missing required setting(s): {', '.join(missing)}")
    return ProviderSettings(
        enabled=_parse_enabled(values.get("enabled", ""), section),
        country=str(values.get("country") or "").strip().upper(),
        locale=str(values.get("locale") or "").strip(),
    )
