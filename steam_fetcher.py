import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from config import STEAM_API_KEY

logger = logging.getLogger(__name__)

STEAM_LIVE_LEAGUE_GAMES = "https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/"
STEAM_LIVE_CACHE_TTL_SECONDS = 20
_live_cache = {"expires_at": 0.0, "games": []}


def _redact_steam_key(text: object) -> str:
    value = str(text)
    if STEAM_API_KEY:
        value = value.replace(STEAM_API_KEY, "[redacted]")
    try:
        parts = urlsplit(value)
        if parts.query:
            query = urlencode(
                (key, "[redacted]" if key.lower() == "key" else item_value)
                for key, item_value in parse_qsl(parts.query, keep_blank_values=True)
            )
            value = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        pass
    return value


def has_steam_api_key() -> bool:
    return bool(STEAM_API_KEY)


def get_live_league_games() -> list[dict]:
    if not STEAM_API_KEY:
        return []

    now = time.time()
    if now < float(_live_cache.get("expires_at") or 0):
        return list(_live_cache.get("games") or [])

    try:
        response = requests.get(
            STEAM_LIVE_LEAGUE_GAMES,
            params={"key": STEAM_API_KEY, "format": "json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("Steam live request failed: %s", _redact_steam_key(exc))
        return []

    if response.status_code != 200:
        logger.warning("Steam live returned HTTP %s: %s", response.status_code, response.text[:200])
        return []

    try:
        data = response.json()
    except ValueError:
        logger.warning("Steam live returned invalid JSON.")
        return []

    games = ((data.get("result") or {}).get("games")) or []
    _live_cache["games"] = games if isinstance(games, list) else []
    _live_cache["expires_at"] = now + STEAM_LIVE_CACHE_TTL_SECONDS
    return list(_live_cache["games"])


def get_live_league_game(match_id: int) -> dict:
    for game in get_live_league_games():
        if int(game.get("match_id") or 0) == int(match_id):
            return game
    return {}
