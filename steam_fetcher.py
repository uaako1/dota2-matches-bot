import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import STEAM_API_KEY
from src.core import shared_http

logger = logging.getLogger(__name__)

STEAM_LIVE_LEAGUE_GAMES = "https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/"
STEAM_LIVE_CACHE_TTL_SECONDS = 20
STEAM_ERROR_COOLDOWN_SECONDS = int(os.getenv("STEAM_ERROR_COOLDOWN_SECONDS", "60"))
_live_cache = {"expires_at": 0.0, "games": []}
_steam_blocked_until = 0.0
_steam_last_status: dict[str, object] = {}


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


def get_steam_health() -> dict:
    now = time.time()
    blocked_until = float(_steam_blocked_until or 0)
    return {
        "blocked": blocked_until > now,
        "blocked_until": int(blocked_until) if blocked_until > now else 0,
        "blocked_remaining_seconds": max(0, int(blocked_until - now)),
        "last_status": dict(_steam_last_status),
    }


def get_live_league_games() -> list[dict]:
    global _steam_blocked_until
    if not STEAM_API_KEY:
        return []

    now = time.time()
    if now < float(_live_cache.get("expires_at") or 0):
        return list(_live_cache.get("games") or [])
    if _steam_blocked_until > now:
        _steam_last_status["live"] = {
            "status": "cooldown",
            "time": int(now),
            "blocked_until": int(_steam_blocked_until),
        }
        logger.info("Steam cooldown active for %ss; skipped live games", int(_steam_blocked_until - now))
        return []

    response = shared_http.get(
        STEAM_LIVE_LEAGUE_GAMES,
        params={"key": STEAM_API_KEY, "format": "json"},
        timeout=20,
    )
    if response is None:
        _steam_blocked_until = time.time() + STEAM_ERROR_COOLDOWN_SECONDS
        _steam_last_status["live"] = {
            "status": "request_error",
            "time": int(time.time()),
            "blocked_until": int(_steam_blocked_until),
        }
        logger.warning("Steam live request failed. Cooling down for %ss.", STEAM_ERROR_COOLDOWN_SECONDS)
        return []

    if response.status_code != 200:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                cooldown_seconds = int(retry_after) if retry_after else STEAM_ERROR_COOLDOWN_SECONDS
            except ValueError:
                cooldown_seconds = STEAM_ERROR_COOLDOWN_SECONDS
            cooldown_seconds = max(30, min(cooldown_seconds, 10 * 60))
            _steam_blocked_until = time.time() + cooldown_seconds
        elif response.status_code >= 500:
            cooldown_seconds = STEAM_ERROR_COOLDOWN_SECONDS
            _steam_blocked_until = time.time() + cooldown_seconds
        else:
            cooldown_seconds = 0
        _steam_last_status["live"] = {
            "status": response.status_code,
            "time": int(time.time()),
            "blocked_until": int(_steam_blocked_until) if cooldown_seconds else 0,
        }
        logger.warning("Steam live returned HTTP %s: %s", response.status_code, _redact_steam_key(response.text[:200]))
        return []

    try:
        data = response.json()
    except ValueError:
        _steam_last_status["live"] = {"status": "invalid_json", "time": int(time.time())}
        logger.warning("Steam live returned invalid JSON.")
        return []

    games = ((data.get("result") or {}).get("games")) or []
    _steam_last_status["live"] = {"status": 200, "time": int(time.time())}
    _live_cache["games"] = games if isinstance(games, list) else []
    _live_cache["expires_at"] = now + STEAM_LIVE_CACHE_TTL_SECONDS
    return list(_live_cache["games"])


def get_live_league_game(match_id: int) -> dict:
    for game in get_live_league_games():
        if int(game.get("match_id") or 0) == int(match_id):
            return game
    return {}
