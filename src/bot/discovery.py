from __future__ import annotations

import time

from config import (
    ACTIVE_LEAGUE_LOOKBACK_DAYS,
    LIVE_MATCHES_FETCH_LIMIT,
    RECENT_MATCHES_FETCH_LIMIT,
    SAFETY_MATCHES_FETCH_LIMIT,
    TIER1_LEAGUES,
    is_allowed_tier1_league,
    resolve_tier1_league_name,
)
from opendota_discovery import get_live_league_matches, get_match_snapshot, get_recent_pro_matches
from src.bot.readiness import snapshot_has_final_result
from src.bot.runtime_state import state
from storage import (
    forget_live_announcement,
    get_sent_set,
    get_tracked_live_matches,
    remove_tracked_live_match,
)

PROCESS_STARTED_AT = int(time.time())
RECOVERY_STARTUP_GRACE_SECONDS = 5 * 60
RECENT_FINISHED_SAFETY_LOOKBACK_SECONDS = 4 * 60 * 60


def get_active_tier1_league_ids() -> set[int]:
    league_ids = set(TIER1_LEAGUES)
    for match in get_recent_pro_matches(league_ids, take=RECENT_MATCHES_FETCH_LIMIT):
        if is_allowed_tier1_league(match.get("leagueid"), match.get("league_name") or ""):
            league_ids.add(int(match.get("leagueid") or 0))
    return league_ids


def get_recent_configured_matches() -> list[dict]:
    cutoff = int(time.time()) - ACTIVE_LEAGUE_LOOKBACK_DAYS * 24 * 60 * 60
    live_ids = {match["match_id"] for match in get_live_configured_matches()}
    matches = get_recent_pro_matches(get_active_tier1_league_ids(), take=RECENT_MATCHES_FETCH_LIMIT)
    normalized = []
    for match in matches:
        if int(match.get("start_time") or 0) < cutoff:
            continue
        if int(match["match_id"]) in live_ids:
            continue
        match["league_name"] = resolve_tier1_league_name(match.get("leagueid"), match.get("league_name"))
        normalized.append(match)
    return normalized


def get_raw_configured_live_rows() -> list[dict]:
    league_ids = get_active_tier1_league_ids()
    live_matches = get_live_league_matches(league_ids, take=LIVE_MATCHES_FETCH_LIMIT)
    for match in live_matches:
        match["league_name"] = resolve_tier1_league_name(match.get("leagueid"), match.get("league_name"))
    return live_matches


def filter_current_live_matches(live_matches: list[dict]) -> list[dict]:
    now = int(time.time())
    filtered = []
    for match in live_matches:
        deactivate_time = int(match.get("deactivate_time") or 0)
        last_update_time = int(match.get("last_update_time") or 0)
        if deactivate_time:
            continue
        if last_update_time and now - last_update_time > 15 * 60:
            continue
        filtered.append(match)
    return filtered


def get_finished_tracked_matches(current_live_ids: set[int] | None = None) -> list[dict]:
    now = int(time.time())
    if current_live_ids is None:
        current_live_ids = {int(match["match_id"]) for match in get_live_configured_matches()}
    tracked = get_tracked_live_matches(state)
    finished = []
    for match_id, match in tracked.items():
        snapshot = get_match_snapshot(match_id)
        if match_id in current_live_ids and not snapshot_has_final_result(snapshot):
            continue
        match["match_id"] = int(match.get("match_id") or match_id)
        start_time = int(match.get("start_time") or 0)
        if start_time and now - start_time > 12 * 60 * 60:
            remove_tracked_live_match(state, match_id)
            forget_live_announcement(state, match_id)
            continue
        finished.append(match)
    finished.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    return finished


def get_recently_deactivated_matches(raw_live_rows: list[dict] | None = None) -> list[dict]:
    now = int(time.time())
    sent = get_sent_set(state)
    tracked = get_tracked_live_matches(state)
    recovered = []
    for match in raw_live_rows if raw_live_rows is not None else get_raw_configured_live_rows():
        match_id = int(match["match_id"])
        deactivate_time = int(match.get("deactivate_time") or 0)
        if not deactivate_time:
            continue
        if deactivate_time < PROCESS_STARTED_AT - RECOVERY_STARTUP_GRACE_SECONDS:
            continue
        if deactivate_time <= now and now - deactivate_time > 2 * 60 * 60:
            continue
        if match_id in sent or match_id in tracked:
            continue
        recovered.append(match)
    recovered.sort(key=lambda item: int(item.get("deactivate_time") or 0), reverse=True)
    return recovered


def get_recent_finished_safety_matches(current_live_ids: set[int] | None = None) -> list[dict]:
    now = int(time.time())
    sent = get_sent_set(state)
    tracked = get_tracked_live_matches(state)
    current_live_ids = current_live_ids or set()
    candidates = []

    for match in get_recent_pro_matches(get_active_tier1_league_ids(), take=SAFETY_MATCHES_FETCH_LIMIT):
        match_id = int(match.get("match_id") or 0)
        if not match_id:
            continue
        if match_id in sent or match_id in tracked or match_id in current_live_ids:
            continue

        start_time = int(match.get("start_time") or 0)
        if not start_time or now - start_time > RECENT_FINISHED_SAFETY_LOOKBACK_SECONDS:
            continue
        if start_time < PROCESS_STARTED_AT - RECOVERY_STARTUP_GRACE_SECONDS:
            continue

        league_id = int(match.get("leagueid") or 0)
        if not is_allowed_tier1_league(league_id, match.get("league_name") or ""):
            continue

        snapshot = get_match_snapshot(match_id)
        if not snapshot_has_final_result(snapshot):
            continue

        match["league_name"] = resolve_tier1_league_name(league_id, match.get("league_name"))
        match["duration"] = int(snapshot.get("duration") or match.get("duration") or 0)
        candidates.append(match)

    candidates.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    return candidates


def get_live_configured_matches() -> list[dict]:
    return filter_current_live_matches(get_raw_configured_live_rows())
