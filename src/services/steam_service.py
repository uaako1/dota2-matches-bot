from __future__ import annotations

from src.core.api_client import APIClient
from src.config.settings import settings

STEAM_LIVE_LEAGUE_GAMES = "https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/"


class SteamService:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    async def get_live_games(self) -> list[dict]:
        if not settings.steam_api_key:
            return []
        data = await self.api_client.get(
            STEAM_LIVE_LEAGUE_GAMES,
            params={"key": settings.steam_api_key, "format": "json"},
            use_cache=False,
        )
        return ((data or {}).get("result") or {}).get("games") or []

    async def get_live_game(self, match_id: int) -> dict:
        for game in await self.get_live_games():
            if int(game.get("match_id") or 0) == int(match_id):
                return game
        return {}
