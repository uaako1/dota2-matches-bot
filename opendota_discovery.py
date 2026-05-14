import logging
import os
import time
import json
from pathlib import Path

import requests

from config import STATE_FILE, is_allowed_tier1_league

logger = logging.getLogger(__name__)

OPENDOTA_PRO_MATCHES = "https://api.opendota.com/api/proMatches"
OPENDOTA_LIVE = "https://api.opendota.com/api/live"
OPENDOTA_MATCH = "https://api.opendota.com/api/matches/{match_id}"
OPENDOTA_TEAM = "https://api.opendota.com/api/teams/{team_id}"
OPENDOTA_PLAYER = "https://api.opendota.com/api/players/{account_id}"
OPENDOTA_LEAGUE_MATCHES = "https://api.opendota.com/api/leagues/{league_id}/matches"

OPENDOTA_429_COOLDOWN_SECONDS = int(os.getenv("OPENDOTA_429_COOLDOWN_SECONDS", "300"))
_opendota_blocked_until = 0.0
_opendota_last_status: dict[str, object] = {}
_team_cache: dict[int, dict] = {}
_player_cache: dict[int, dict] = {}
_persistent_lookup_cache_loaded = False
_persistent_lookup_cache: dict[str, dict[str, dict]] = {"teams": {}, "players": {}}


def _lookup_cache_path() -> Path:
    return Path(STATE_FILE).parent / "opendota_lookup_cache.json"


def _load_persistent_lookup_cache() -> None:
    global _persistent_lookup_cache_loaded, _persistent_lookup_cache
    if _persistent_lookup_cache_loaded:
        return
    _persistent_lookup_cache_loaded = True
    path = _lookup_cache_path()
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("Could not load OpenDota lookup cache %s: %s", path, exc)
        return
    if not isinstance(data, dict):
        return
    teams = data.get("teams") if isinstance(data.get("teams"), dict) else {}
    players = data.get("players") if isinstance(data.get("players"), dict) else {}
    _persistent_lookup_cache = {"teams": teams, "players": players}
    for key, value in teams.items():
        if str(key).isdigit() and isinstance(value, dict):
            _team_cache[int(key)] = dict(value)
    for key, value in players.items():
        if str(key).isdigit() and isinstance(value, dict):
            _player_cache[int(key)] = dict(value)


def _save_persistent_lookup_cache() -> None:
    path = _lookup_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(_persistent_lookup_cache, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
    except Exception as exc:
        logger.warning("Could not save OpenDota lookup cache %s: %s", path, exc)


def _remember_lookup_cache(kind: str, key: int, payload: dict) -> None:
    if not payload:
        return
    _load_persistent_lookup_cache()
    bucket = _persistent_lookup_cache.setdefault(kind, {})
    bucket[str(int(key))] = dict(payload)
    if len(bucket) > 3000:
        for old_key in list(bucket.keys())[: len(bucket) - 3000]:
            bucket.pop(old_key, None)
    _save_persistent_lookup_cache()


def _endpoint_name(url: str) -> str:
    if "/proMatches" in url:
        return "proMatches"
    if "/live" in url:
        return "live"
    if "/matches/" in url:
        return "matches"
    if "/teams/" in url:
        return "teams"
    if "/players/" in url:
        return "players"
    if "/leagues/" in url:
        return "leagues"
    return "unknown"


def get_opendota_health() -> dict:
    now = time.time()
    blocked_until = float(_opendota_blocked_until or 0)
    return {
        "blocked": blocked_until > now,
        "blocked_until": int(blocked_until) if blocked_until > now else 0,
        "blocked_remaining_seconds": max(0, int(blocked_until - now)),
        "last_status": dict(_opendota_last_status),
    }


def _get_json(url: str):
    global _opendota_blocked_until

    endpoint = _endpoint_name(url)
    now = time.time()
    if _opendota_blocked_until > now:
        _opendota_last_status[endpoint] = {
            "status": "cooldown",
            "url": url,
            "time": int(now),
            "blocked_until": int(_opendota_blocked_until),
        }
        logger.info(
            "OpenDota cooldown active for %ss; skipped %s",
            int(_opendota_blocked_until - now),
            endpoint,
        )
        return None

    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        _opendota_last_status[endpoint] = {
            "status": "request_error",
            "url": url,
            "time": int(now),
            "error": str(exc),
        }
        logger.warning("OpenDota request failed for %s: %s", url, exc)
        return None

    if response.status_code != 200:
        _opendota_last_status[endpoint] = {
            "status": response.status_code,
            "url": url,
            "time": int(time.time()),
        }
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                cooldown_seconds = int(retry_after) if retry_after else OPENDOTA_429_COOLDOWN_SECONDS
            except ValueError:
                cooldown_seconds = OPENDOTA_429_COOLDOWN_SECONDS
            cooldown_seconds = max(60, min(cooldown_seconds, 10 * 60))
            _opendota_blocked_until = time.time() + cooldown_seconds
            _opendota_last_status[endpoint]["blocked_until"] = int(_opendota_blocked_until)
            logger.warning(
                "OpenDota returned HTTP 429 for %s; blocking OpenDota requests for %ss",
                url,
                cooldown_seconds,
            )
            return None
        logger.warning("OpenDota returned HTTP %s for %s", response.status_code, url)
        return None

    try:
        data = response.json()
        _opendota_last_status[endpoint] = {
            "status": 200,
            "url": url,
            "time": int(time.time()),
        }
        return data
    except ValueError:
        _opendota_last_status[endpoint] = {
            "status": "invalid_json",
            "url": url,
            "time": int(time.time()),
        }
        logger.warning("OpenDota returned invalid JSON for %s", url)
        return None


def get_recent_pro_matches(league_ids: set[int] | list[int], take: int = 50) -> list[dict]:
    wanted = {int(x) for x in league_ids}
    if not wanted:
        return []

    rows = _get_json(OPENDOTA_PRO_MATCHES) or []

    matches = []
    for row in rows:
        league_id = int(row.get("leagueid") or 0)
        league_name = row.get("league_name") or ""
        if league_id not in wanted and not is_allowed_tier1_league(league_id, league_name):
            continue
        match_id = row.get("match_id")
        if not match_id:
            continue
        matches.append(
            {
                "match_id": int(match_id),
                "leagueid": league_id,
                "league_name": league_name,
                "start_time": int(row.get("start_time") or 0),
                "radiant_name": row.get("radiant_name") or "Radiant",
                "dire_name": row.get("dire_name") or "Dire",
            }
        )

    matches.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    return matches[:take]


def get_live_league_matches(league_ids: set[int] | list[int], take: int = 50) -> list[dict]:
    wanted = {int(x) for x in league_ids}
    if not wanted:
        return []

    rows = _get_json(OPENDOTA_LIVE) or []

    matches = []
    for row in rows:
        league_id = int(row.get("league_id") or 0)
        league_name = row.get("league_name") or row.get("league_name_raw") or row.get("league") or ""
        if league_id not in wanted and not is_allowed_tier1_league(league_id, league_name):
            continue
        match_id = row.get("match_id")
        if not match_id:
            continue
        matches.append(
            {
                "match_id": int(match_id),
                "leagueid": league_id,
                "league_name": league_name,
                "start_time": int(row.get("activate_time") or 0),
                "game_time": int(row.get("game_time") or 0),
                "last_update_time": int(row.get("last_update_time") or 0),
                "deactivate_time": int(row.get("deactivate_time") or 0),
                "radiant_name": row.get("team_name_radiant") or "Radiant",
                "dire_name": row.get("team_name_dire") or "Dire",
                "radiant_score": int(row.get("radiant_score") or 0),
                "dire_score": int(row.get("dire_score") or 0),
                "radiant_team_id": int(row.get("team_id_radiant") or 0),
                "dire_team_id": int(row.get("team_id_dire") or 0),
                "radiant_logo_id": str(row.get("team_logo_radiant") or "").strip(),
                "dire_logo_id": str(row.get("team_logo_dire") or "").strip(),
                "players": row.get("players") or [],
            }
        )

    matches.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    return matches[:take]


def get_match_snapshot(match_id: int) -> dict:
    return _get_json(OPENDOTA_MATCH.format(match_id=int(match_id))) or {}


def get_league_matches(league_id: int) -> list[dict]:
    league_id = int(league_id or 0)
    if not league_id:
        return []
    rows = _get_json(OPENDOTA_LEAGUE_MATCHES.format(league_id=league_id)) or []
    return rows if isinstance(rows, list) else []


def get_team_info(team_id: int) -> dict:
    team_id = int(team_id or 0)
    if not team_id:
        return {}
    _load_persistent_lookup_cache()
    if team_id in _team_cache:
        return dict(_team_cache[team_id])
    data = _get_json(OPENDOTA_TEAM.format(team_id=team_id)) or {}
    if not data:
        return {}
    payload = {
        "team_id": int(data.get("team_id") or team_id),
        "name": data.get("name") or "",
        "tag": data.get("tag") or "",
        "logo_url": data.get("logo_url") or "",
    }
    _team_cache[team_id] = payload
    _remember_lookup_cache("teams", team_id, payload)
    return dict(payload)


def clear_opendota_memory_cache() -> None:
    _team_cache.clear()
    _player_cache.clear()


def get_player_info(account_id: int) -> dict:
    account_id = int(account_id or 0)
    if not account_id:
        return {}
    _load_persistent_lookup_cache()
    if account_id in _player_cache:
        return dict(_player_cache[account_id])
    data = _get_json(OPENDOTA_PLAYER.format(account_id=account_id)) or {}
    if not data:
        return {}
    profile = data.get("profile") or {}
    payload = {
        "account_id": account_id,
        "personaname": profile.get("personaname") or "",
        "name": profile.get("name") or "",
        "steamid": profile.get("steamid") or "",
    }
    _player_cache[account_id] = payload
    _remember_lookup_cache("players", account_id, payload)
    return dict(payload)
