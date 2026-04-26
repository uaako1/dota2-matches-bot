import json
import logging
import time
from copy import deepcopy
from pathlib import Path

from config import STATE_FILE

logger = logging.getLogger(__name__)

DEFAULT_STATE = {
    "sent_matches": [],
    "announced_live_matches": [],
    "tracked_live_matches": {},
    "draft_cache": {},
}

DRAFT_CACHE_TTL_SECONDS = 24 * 60 * 60


def prune_draft_cache(state: dict, now: int | None = None, ttl_seconds: int = DRAFT_CACHE_TTL_SECONDS) -> None:
    cache = state.get("draft_cache")
    if not isinstance(cache, dict):
        state["draft_cache"] = {}
        return

    now = int(now or time.time())
    for key, payload in list(cache.items()):
        if not isinstance(payload, dict):
            cache.pop(key, None)
            continue

        updated_at = int(payload.get("updated_at") or 0)
        if updated_at and now - updated_at > ttl_seconds:
            cache.pop(key, None)


def load_state() -> dict:
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return deepcopy(DEFAULT_STATE)

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Could not load state file %s: %s", path, exc)
        return deepcopy(DEFAULT_STATE)

    state = deepcopy(DEFAULT_STATE)
    state.update(data if isinstance(data, dict) else {})
    state["sent_matches"] = [int(x) for x in state.get("sent_matches", []) if str(x).isdigit()]
    state["announced_live_matches"] = [
        int(x) for x in state.get("announced_live_matches", []) if str(x).isdigit()
    ]
    tracked = state.get("tracked_live_matches")
    state["tracked_live_matches"] = tracked if isinstance(tracked, dict) else {}
    draft_cache = state.get("draft_cache")
    state["draft_cache"] = draft_cache if isinstance(draft_cache, dict) else {}
    prune_draft_cache(state)
    return state


def save_state(state: dict) -> None:
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    prune_draft_cache(state)

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    tmp_path.replace(path)


def get_sent_set(state: dict) -> set[int]:
    return {int(x) for x in state.get("sent_matches", [])}


def remember_sent_match(state: dict, match_id: int, max_sent: int = 2000) -> None:
    sent = [int(x) for x in state.get("sent_matches", [])]
    if match_id not in sent:
        sent.append(int(match_id))
    state["sent_matches"] = sent[-max_sent:]


def get_announced_live_set(state: dict) -> set[int]:
    return {int(x) for x in state.get("announced_live_matches", [])}


def remember_live_announcement(state: dict, match_id: int, max_items: int = 1000) -> None:
    announced = [int(x) for x in state.get("announced_live_matches", [])]
    if match_id not in announced:
        announced.append(int(match_id))
    state["announced_live_matches"] = announced[-max_items:]


def forget_live_announcement(state: dict, match_id: int) -> None:
    state["announced_live_matches"] = [
        int(x) for x in state.get("announced_live_matches", [])
        if int(x) != int(match_id)
    ]


def get_tracked_live_matches(state: dict) -> dict[int, dict]:
    tracked = state.get("tracked_live_matches") or {}
    normalized: dict[int, dict] = {}
    for match_id, payload in tracked.items():
        try:
            normalized[int(match_id)] = dict(payload or {})
        except Exception:
            continue
    return normalized


def upsert_tracked_live_match(state: dict, match_summary: dict) -> None:
    tracked = state.setdefault("tracked_live_matches", {})
    match_id = int(match_summary["match_id"])
    existing = dict(tracked.get(str(match_id)) or {})
    existing.update(match_summary)
    tracked[str(match_id)] = existing


def mark_tracked_live_preview_posted(state: dict, match_id: int) -> None:
    tracked = state.setdefault("tracked_live_matches", {})
    entry = dict(tracked.get(str(int(match_id))) or {})
    entry["preview_posted"] = True
    tracked[str(int(match_id))] = entry


def remove_tracked_live_match(state: dict, match_id: int) -> None:
    tracked = state.setdefault("tracked_live_matches", {})
    tracked.pop(str(int(match_id)), None)


def get_cached_draft(state: dict, match_id: int) -> dict:
    cache = state.get("draft_cache") or {}
    payload = cache.get(str(int(match_id))) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def remember_draft_cache(state: dict, match_id: int, players: list[dict], bans: list[dict], source: str = "", max_items: int = 500) -> None:
    if not players and not bans:
        return

    cache = state.setdefault("draft_cache", {})
    key = str(int(match_id))
    existing = dict(cache.get(key) or {})
    existing_players = existing.get("players") if isinstance(existing.get("players"), list) else []
    existing_bans = existing.get("bans") if isinstance(existing.get("bans"), list) else []

    if len(players or []) >= len(existing_players):
        existing["players"] = players or []
    if len(bans or []) >= len(existing_bans):
        existing["bans"] = bans or []
        existing["bans_source"] = source or existing.get("bans_source") or ""

    existing["updated_at"] = int(time.time())
    cache[key] = existing
    if len(cache) > max_items:
        for old_key in list(cache.keys())[: len(cache) - max_items]:
            cache.pop(old_key, None)
