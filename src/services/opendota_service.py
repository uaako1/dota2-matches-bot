from __future__ import annotations

from src.core.api_client import APIClient

BASE = "https://api.opendota.com/api"


class OpenDotaService:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    async def get_recent_pro_matches(self) -> list[dict]:
        data = await self.api_client.get(f"{BASE}/proMatches", use_cache=False)
        return data if isinstance(data, list) else []

    async def get_live_matches(self) -> list[dict]:
        data = await self.api_client.get(f"{BASE}/live", use_cache=False)
        return data if isinstance(data, list) else []

    async def get_match_snapshot(self, match_id: int) -> dict:
        data = await self.api_client.get(f"{BASE}/matches/{int(match_id)}", use_cache=False)
        return data if isinstance(data, dict) else {}

    async def get_league_matches(self, league_id: int) -> list[dict]:
        data = await self.api_client.get(f"{BASE}/leagues/{int(league_id)}/matches", use_cache=False)
        return data if isinstance(data, list) else []
