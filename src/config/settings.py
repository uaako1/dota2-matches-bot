from __future__ import annotations

import os
from dataclasses import dataclass

try:
    import config as legacy_config
except Exception:
    legacy_config = None


def _legacy(name: str, default: str = "") -> str:
    if legacy_config is None:
        return default
    return str(getattr(legacy_config, name, default) or default).strip()


@dataclass(slots=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", _legacy("TELEGRAM_TOKEN")).strip()
    channel_id: str = os.getenv("CHANNEL_ID", _legacy("CHANNEL_ID")).strip()
    stratz_token: str = os.getenv("STRATZ_TOKEN", _legacy("STRATZ_TOKEN")).strip()
    steam_api_key: str = os.getenv("STEAM_API_KEY", _legacy("STEAM_API_KEY")).strip()
    check_interval_minutes: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "4"))
    max_matches_per_check: int = int(os.getenv("MAX_MATCHES_PER_CHECK", "10"))
    post_delay_seconds: int = int(os.getenv("POST_DELAY_SECONDS", "1"))
    cache_dir: str = os.getenv("CACHE_DIR", "data/cache")
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", str(24 * 60 * 60)))

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.telegram_token:
            errors.append("Missing TELEGRAM_TOKEN")
        if not self.channel_id:
            errors.append("Missing CHANNEL_ID")
        return errors


settings = Settings()
