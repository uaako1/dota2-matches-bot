from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import md5
from pathlib import Path
from typing import Any


class CacheManager:
    def __init__(self, cache_dir: Path, ttl_seconds: int = 24 * 60 * 60):
        self.cache_dir = cache_dir
        self.ttl = timedelta(seconds=int(ttl_seconds))
        self.cache_file = self.cache_dir / "api_cache.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            self._data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self.cache_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

    @staticmethod
    def build_key(url: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> str:
        raw = json.dumps(
            {"url": url, "params": params or {}, "body": body or {}},
            sort_keys=True,
            ensure_ascii=False,
        )
        return md5(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        payload = self._data.get(key)
        if not payload:
            return None
        stamp = payload.get("timestamp")
        if not stamp:
            return None
        try:
            ts = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if datetime.now(timezone.utc) - ts > self.ttl:
            self._data.pop(key, None)
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        self._data[key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._save()

    def clear(self) -> None:
        self._data = {}
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except OSError:
            return
