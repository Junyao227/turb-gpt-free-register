from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .provider_config import ProviderConfigError, ProviderSettings, load_provider_settings


@dataclass(frozen=True)
class ProviderDefinition:
    public_type: str
    native_type: str
    display_name: str
    config_section: str
    queue_path: str


@dataclass(frozen=True)
class ResolvedProvider:
    definition: ProviderDefinition
    settings: ProviderSettings


PROVIDERS: dict[str, ProviderDefinition] = {
    "pix": ProviderDefinition("pix", "pix", "PIX", "providers.pix", "/qr"),
    "upi": ProviderDefinition("upi", "upi", "UPI", "providers.upi", "/in-qr"),
    "kakao_pay": ProviderDefinition(
        "kakao_pay",
        "korea",
        "Kakao Pay",
        "providers.kakao_pay",
        "/kr-qr",
    ),
    "ideal": ProviderDefinition("ideal", "ideal", "iDEAL", "providers.ideal", "/nl-qr"),
}


def supported_provider_types() -> tuple[str, ...]:
    return tuple(PROVIDERS.keys())


def enabled_provider_metadata(config_path: Path | None = None) -> tuple[dict[str, str], ...]:
    items: list[dict[str, str]] = []
    for definition in PROVIDERS.values():
        settings = load_provider_settings(definition.config_section, config_path)
        if not settings.enabled:
            continue
        items.append(
            {
                "public_type": definition.public_type,
                "native_type": definition.native_type,
                "display_name": definition.display_name,
                "country": settings.country,
                "locale": settings.locale,
                "queue_path": definition.queue_path,
            }
        )
    return tuple(items)


def resolve_provider(link_type: str, config_path: Path | None = None) -> ResolvedProvider:
    public_type = str(link_type or "").strip().lower()
    definition = PROVIDERS.get(public_type)
    if definition is None:
        supported = " / ".join(supported_provider_types())
        raise ProviderConfigError(f"unsupported link_type '{public_type or '-'}'; supported: {supported}")

    settings = load_provider_settings(definition.config_section, config_path)
    if not settings.enabled:
        raise ProviderConfigError(f"provider '{definition.display_name}' is disabled by [{definition.config_section}]")
    return ResolvedProvider(definition=definition, settings=settings)
