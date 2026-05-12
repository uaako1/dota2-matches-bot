import logging
from functools import lru_cache

import requests

from config import is_allowed_tier1_league

logger = logging.getLogger(__name__)

OPENDOTA_PRO_MATCHES = "https://api.opendota.com/api/proMatches"
OPENDOTA_LIVE = "https://api.opendota.com/api/live"
OPENDOTA_MATCH = "https://api.opendota.com/api/matches/{match_id}"
OPENDOTA_TEAM = "https://api.opendota.com/api/teams/{team_id}"
OPENDOTA_PLAYER = "https://api.opendota.com/api/players/{account_id}"
OPENDOTA_LEAGUE_MATCHES = "https://api.opendota.com/api/leagues/{league_id}/matches"


def _get_json(url: str):
    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        logger.warning("OpenDota request failed for %s: %s", url, exc)
        return None

    if response.status_code != 200:
        logger.warning("OpenDota returned HTTP %s for %s", response.status_code, url)
        return None

    try:
        return response.json()
    except ValueError:
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


@lru_cache(maxsize=256)
def get_team_info(team_id: int) -> dict:
    team_id = int(team_id or 0)
    if not team_id:
        return {}
    data = _get_json(OPENDOTA_TEAM.format(team_id=team_id)) or {}
    return {
        "team_id": int(data.get("team_id") or team_id),
        "name": data.get("name") or "",
        "tag": data.get("tag") or "",
        "logo_url": data.get("logo_url") or "",
    }


@lru_cache(maxsize=2048)
def get_player_info(account_id: int) -> dict:
    account_id = int(account_id or 0)
    if not account_id:
        return {}
    data = _get_json(OPENDOTA_PLAYER.format(account_id=account_id)) or {}
    profile = data.get("profile") or {}
    return {
        "account_id": account_id,
        "personaname": profile.get("personaname") or "",
        "name": profile.get("name") or "",
        "steamid": profile.get("steamid") or "",
    }
