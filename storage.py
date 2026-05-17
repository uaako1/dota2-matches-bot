import json
import logging
import time
from copy import deepcopy
from pathlib import Path

from config import STATE_FILE

logger = logging.getLogger(__name__)

DEFAULT_STATE = {
    "sent_matches": [],
    "previewed_matches": [],
    "announced_live_matches": [],
    "tracked_live_matches": {},
    "draft_cache": {},
    "match_posts": {},
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
    state["previewed_matches"] = [int(x) for x in state.get("previewed_matches", []) if str(x).isdigit()]
    state["announced_live_matches"] = [
        int(x) for x in state.get("announced_live_matches", []) if str(x).isdigit()
    ]
    tracked = state.get("tracked_live_matches")
    state["tracked_live_matches"] = tracked if isinstance(tracked, dict) else {}
    draft_cache = state.get("draft_cache")
    state["draft_cache"] = draft_cache if isinstance(draft_cache, dict) else {}
    match_posts = state.get("match_posts")
    state["match_posts"] = match_posts if isinstance(match_posts, dict) else {}
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


def get_previewed_set(state: dict) -> set[int]:
    return {int(x) for x in state.get("previewed_matches", [])}


def remember_previewed_match(state: dict, match_id: int, max_items: int = 2000) -> None:
    previewed = [int(x) for x in state.get("previewed_matches", [])]
    if int(match_id) not in previewed:
        previewed.append(int(match_id))
    state["previewed_matches"] = previewed[-max_items:]


def get_match_post_record(state: dict, match_id: int) -> dict:
    posts = state.get("match_posts") or {}
    payload = posts.get(str(int(match_id))) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def has_match_posted(state: dict, match_id: int, kind: str) -> bool:
    record = get_match_post_record(state, match_id)
    posted = record.get(kind)
    return isinstance(posted, dict) and bool(posted.get("posted_at"))


def remember_match_post(state: dict, match_id: int, kind: str, details: dict, message_id: int | None = None, max_items: int = 3000) -> None:
    posts = state.setdefault("match_posts", {})
    key = str(int(match_id))
    record = dict(posts.get(key) or {})
    payload = {
        "posted_at": int(time.time()),
        "message_id": int(message_id) if message_id else None,
        "leagueid": int(details.get("leagueid") or details.get("league_id") or 0),
        "league_name": details.get("league_name") or "",
        "series_id": int(details.get("series_id") or 0),
        "series_type": details.get("series_type"),
        "best_of": details.get("best_of"),
        "game_number": details.get("game_number"),
        "radiant_name": details.get("radiant_name") or "",
        "dire_name": details.get("dire_name") or "",
        "radiant_team_id": int((details.get("radiant_team") or {}).get("id") or details.get("radiant_team_id") or 0),
        "dire_team_id": int((details.get("dire_team") or {}).get("id") or details.get("dire_team_id") or 0),
        "radiant_score": int(details.get("radiant_score") or 0),
        "dire_score": int(details.get("dire_score") or 0),
    }
    record[kind] = payload
    posts[key] = record
    if len(posts) > max_items:
        for old_key in list(posts.keys())[: len(posts) - max_items]:
            posts.pop(old_key, None)


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
