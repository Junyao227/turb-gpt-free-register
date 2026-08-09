from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile


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


def write_provider_settings(
    section: str,
    values: dict[str, str],
    path: Path | None = None,
) -> ProviderSettings:
    """Atomically update selected non-secret keys while retaining other INI lines."""
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise ProviderConfigError(f"provider configuration file is missing: {config_path}")

    parser = ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section(section):
        raise ProviderConfigError(f"provider configuration section is missing: [{section}]")

    normalized = {str(key).strip().lower(): str(value).strip() for key, value in values.items()}
    if not normalized:
        return load_provider_settings(section, config_path)

    existing = config_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in existing else "\n"
    lines = existing.splitlines(keepends=True)
    section_header = re.compile(r"^\s*\[(?P<name>[^]]+)\]\s*(?:[;#].*)?$")
    assignment = re.compile(r"^(?P<prefix>\s*)(?P<key>[^=;#\s]+)\s*=.*(?:\r?\n)?$")
    target_index = next(
        (index for index, line in enumerate(lines) if (match := section_header.match(line)) and match.group("name") == section),
        -1,
    )
    if target_index < 0:
        raise ProviderConfigError(f"provider configuration section is missing: [{section}]")

    end_index = next(
        (index for index in range(target_index + 1, len(lines)) if section_header.match(lines[index])),
        len(lines),
    )
    updated: set[str] = set()
    output: list[str] = []
    for index, line in enumerate(lines):
        if target_index < index < end_index:
            match = assignment.match(line)
            key = match.group("key").strip().lower() if match else ""
            if key in normalized:
                output.append(f"{match.group('prefix')}{key} = {normalized[key]}{newline}")
                updated.add(key)
                continue
        output.append(line)

    insertion_index = sum(len(line) for line in output[:end_index])
    additions = "".join(f"{key} = {value}{newline}" for key, value in normalized.items() if key not in updated)
    if additions:
        combined = "".join(output)
        combined = f"{combined[:insertion_index]}{additions}{combined[insertion_index:]}"
    else:
        combined = "".join(output)

    fd, temporary_path = tempfile.mkstemp(prefix=".providers-", suffix=".tmp", dir=str(config_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(combined)
        os.replace(temporary_path, config_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
    return load_provider_settings(section, config_path)
