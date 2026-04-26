from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.models.match import MatchModel
from src.models.player import PlayerModel


class NeutralItemCache:
    def __init__(self, path: str | Path | None = None, ttl_seconds: int = 48 * 60 * 60) -> None:
        self.path = Path(path) if path else None
        self.ttl_seconds = int(ttl_seconds)
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()
        self.prune()

    @staticmethod
    def _keys(player: PlayerModel) -> list[str]:
        keys: list[str] = []
        if player.account_id:
            keys.append(f"account:{player.account_id}")
        if player.hero_id:
            side = "r" if player.is_radiant else "d"
            keys.append(f"sidehero:{side}:{player.hero_id}")
        return keys

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(payload, dict):
            self._data = payload

    def _save(self) -> None:
        if not self.path:
            return
        self.prune(save=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def prune(self, *, save: bool = True) -> None:
        now = int(time.time())
        changed = False
        for match_id in list(self._data):
            bucket = self._data.get(match_id) or {}
            for key in list(bucket):
                updated_at = int((bucket.get(key) or {}).get("updated_at") or 0)
                if not updated_at or now - updated_at > self.ttl_seconds:
                    bucket.pop(key, None)
                    changed = True
            if not bucket:
                self._data.pop(match_id, None)
                changed = True
        if changed and save:
            self._save()

    def remember_match(self, match: MatchModel) -> None:
        self.prune(save=False)
        if not match.match_id:
            return
        bucket = self._data.setdefault(str(match.match_id), {})
        updated_at = int(time.time())
        changed = False
        for player in match.players:
            if not player.neutral_item:
                continue
            entry = {"neutral_item": player.neutral_item, "updated_at": updated_at}
            for key in self._keys(player):
                bucket[key] = entry
                changed = True
        if changed:
            self._save()

    def apply_to_match(self, match: MatchModel) -> None:
        bucket = self._data.get(str(match.match_id)) or {}
        if not bucket:
            return
        for player in match.players:
            if player.neutral_item:
                continue
            for key in self._keys(player):
                entry = bucket.get(key)
                if entry and entry.get("neutral_item"):
                    player.neutral_item = dict(entry["neutral_item"])
                    break

    def clear(self) -> None:
        self._data = {}
        if not self.path:
            return
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            return
