from __future__ import annotations

from src.core.api_client import APIClient
from src.config.settings import settings

STRATZ_GRAPHQL = "https://api.stratz.com/graphql"


class StratzService:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    async def _post_graphql(self, query: str, variables: dict) -> dict | None:
        if not settings.stratz_token:
            return None
        data = await self.api_client.post(
            STRATZ_GRAPHQL,
            json_body={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {settings.stratz_token}"},
            use_cache=False,
        )
        if not isinstance(data, dict):
            return None
        if data.get("errors"):
            return None
        return data

    async def get_live_matches(self) -> list[dict]:
        query = """
        query($leagueIds: [Int]) {
          live {
            matches(request: { leagueIds: $leagueIds, isCompleted: false, isLeague: true, take: 50 }) {
              matchId
              gameTime
              radiantScore
              direScore
            }
          }
        }
        """
        payload = await self._post_graphql(query, {"leagueIds": []})
        return (((payload or {}).get("data") or {}).get("live") or {}).get("matches") or []

    async def get_match_details(self, match_id: int) -> dict | None:
        query = """
        query($id: Long!) {
          match(id: $id) {
            id
            didRadiantWin
            durationSeconds
          }
        }
        """
        payload = await self._post_graphql(query, {"id": int(match_id)})
        return ((payload or {}).get("data") or {}).get("match")
