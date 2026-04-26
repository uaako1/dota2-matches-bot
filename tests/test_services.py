from __future__ import annotations

import unittest
import time

from src.config.settings import settings
from src.models.match import MatchModel
from src.models.player import PlayerModel
from src.services.match_adapter import match_to_legacy_dict, missing_neutral_players
from src.services.match_pipeline import MatchPipelineService
from src.services.neutral_cache import NeutralItemCache
from src.services.opendota_service import OpenDotaService
from src.services.steam_service import SteamService


class FakeAPIClient:
    def __init__(self, payload):
        self.payload = payload

    async def get(self, url, **kwargs):
        return self.payload.get(url, self.payload.get("default"))

    async def post(self, url, **kwargs):
        return self.payload.get(url, self.payload.get("default"))


class FakeSteamService:
    def __init__(self, games):
        self.games = games

    async def get_live_games(self):
        return self.games


class FakeOpenDotaService:
    def __init__(self, live_rows=None, snapshot=None):
        self.live_rows = live_rows or []
        self.snapshot = snapshot or {}

    async def get_live_matches(self):
        return self.live_rows

    async def get_match_snapshot(self, match_id):
        return self.snapshot


class FakeStratzService:
    def __init__(self, match=None):
        self.match = match

    async def get_match_details(self, match_id):
        return self.match


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_opendota_match_snapshot_returns_dict(self) -> None:
        client = FakeAPIClient({"https://api.opendota.com/api/matches/123": {"match_id": 123}})
        service = OpenDotaService(client)  # type: ignore[arg-type]
        result = await service.get_match_snapshot(123)
        self.assertEqual(result["match_id"], 123)

    async def test_steam_live_game_lookup(self) -> None:
        payload = {
            "https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/": {
                "result": {"games": [{"match_id": 77}, {"match_id": 88}]}
            }
        }
        client = FakeAPIClient(payload)
        service = SteamService(client)  # type: ignore[arg-type]
        previous_key = settings.steam_api_key
        settings.steam_api_key = "test-key"
        try:
            result = await service.get_live_game(88)
        finally:
            settings.steam_api_key = previous_key
        self.assertEqual(result["match_id"], 88)

    async def test_match_pipeline_live_tier1_filters_and_merges(self) -> None:
        pipeline = MatchPipelineService(
            FakeSteamService([{"match_id": 10, "game_time": 1234, "radiant_score": 1, "dire_score": 2}]),
            FakeOpenDotaService(
                live_rows=[
                    {
                        "match_id": 10,
                        "league_id": 19543,
                        "team_name_radiant": "Alpha",
                        "team_name_dire": "Beta",
                        "game_time": 1200,
                        "radiant_score": 0,
                        "dire_score": 1,
                        "players": [],
                    },
                    {
                        "match_id": 11,
                        "league_id": 999,
                        "team_name_radiant": "Ignore",
                        "team_name_dire": "Ignore",
                    },
                ]
            ),
            FakeStratzService(),
        )
        rows = await pipeline.get_live_tier1_matches()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].match_id, 10)
        self.assertEqual(rows[0].league_id, 19543)

    async def test_match_pipeline_keeps_steam_only_tier1_live_match(self) -> None:
        pipeline = MatchPipelineService(
            FakeSteamService(
                [
                    {
                        "match_id": 20,
                        "league_id": 19543,
                        "game_time": 777,
                        "radiant_score": 3,
                        "dire_score": 4,
                        "radiant_team": {"team_name": "Steam R"},
                        "dire_team": {"team_name": "Steam D"},
                    }
                ]
            ),
            FakeOpenDotaService(live_rows=[]),
            FakeStratzService(),
        )
        rows = await pipeline.get_live_tier1_matches()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].match_id, 20)
        self.assertEqual(rows[0].radiant_name, "Steam R")

    async def test_match_pipeline_result_uses_snapshot_first(self) -> None:
        pipeline = MatchPipelineService(
            FakeSteamService([]),
            FakeOpenDotaService(
                snapshot={
                    "match_id": 77,
                    "leagueid": 19543,
                    "radiant_name": "R",
                    "dire_name": "D",
                    "radiant_score": 20,
                    "dire_score": 10,
                    "duration": 1000,
                    "radiant_win": True,
                    "players": [{"account_id": 1, "personaname": "p1", "hero_id": 1, "isRadiant": True}],
                }
            ),
            FakeStratzService(match={"id": 77}),
        )
        result = await pipeline.get_result_match(77, 19543)
        self.assertIsNotNone(result)
        self.assertEqual(result.match_id, 77)
        self.assertEqual(result.radiant_name, "R")
        self.assertTrue(result.players[0].is_radiant)

    async def test_match_pipeline_extracts_bans_from_snapshot(self) -> None:
        pipeline = MatchPipelineService(
            FakeSteamService([]),
            FakeOpenDotaService(
                snapshot={
                    "match_id": 78,
                    "leagueid": 19543,
                    "players": [{"account_id": 1, "personaname": "p1", "hero_id": 1, "player_slot": 129}],
                    "picks_bans": [
                        {"is_pick": True, "hero_id": 1, "order": 0},
                        {"is_pick": False, "hero_id": 2, "order": 1},
                    ],
                }
            ),
            FakeStratzService(),
        )
        result = await pipeline.get_result_match(78, 19543)
        self.assertIsNotNone(result)
        self.assertFalse(result.players[0].is_radiant)
        self.assertEqual(result.bans, [{"hero_id": 2, "order": 1}])

    async def test_match_pipeline_applies_cached_live_neutral_to_result(self) -> None:
        neutral_cache = NeutralItemCache()
        pipeline = MatchPipelineService(
            FakeSteamService([]),
            FakeOpenDotaService(
                live_rows=[
                    {
                        "match_id": 79,
                        "league_id": 19543,
                        "players": [
                            {
                                "account_id": 100,
                                "personaname": "p1",
                                "hero_id": 1,
                                "isRadiant": True,
                                "neutral_item": {"id": 999, "short_name": "test_neutral"},
                            }
                        ],
                    }
                ],
                snapshot={
                    "match_id": 79,
                    "leagueid": 19543,
                    "players": [{"account_id": 100, "personaname": "p1", "hero_id": 1, "isRadiant": True}],
                },
            ),
            FakeStratzService(),
            neutral_cache=neutral_cache,
        )

        await pipeline.get_live_tier1_matches()
        result = await pipeline.get_result_match(79, 19543)

        self.assertIsNotNone(result)
        self.assertEqual(result.players[0].neutral_item, {"id": 999, "short_name": "test_neutral"})

    async def test_match_pipeline_does_not_overwrite_result_neutral(self) -> None:
        neutral_cache = NeutralItemCache()
        pipeline = MatchPipelineService(
            FakeSteamService([]),
            FakeOpenDotaService(
                live_rows=[
                    {
                        "match_id": 80,
                        "league_id": 19543,
                        "players": [
                            {
                                "account_id": 100,
                                "hero_id": 1,
                                "isRadiant": True,
                                "neutral_item": {"id": 111, "short_name": "cached"},
                            }
                        ],
                    }
                ],
                snapshot={
                    "match_id": 80,
                    "leagueid": 19543,
                    "players": [
                        {
                            "account_id": 100,
                            "hero_id": 1,
                            "isRadiant": True,
                            "neutral_item": {"id": 222, "short_name": "result"},
                        }
                    ],
                },
            ),
            FakeStratzService(),
            neutral_cache=neutral_cache,
        )

        await pipeline.get_live_tier1_matches()
        result = await pipeline.get_result_match(80, 19543)

        self.assertIsNotNone(result)
        self.assertEqual(result.players[0].neutral_item, {"id": 222, "short_name": "result"})

    async def test_match_pipeline_cached_neutral_fallbacks_to_side_and_hero(self) -> None:
        neutral_cache = NeutralItemCache()
        pipeline = MatchPipelineService(
            FakeSteamService([]),
            FakeOpenDotaService(
                live_rows=[
                    {
                        "match_id": 81,
                        "league_id": 19543,
                        "players": [
                            {
                                "hero_id": 1,
                                "isRadiant": False,
                                "neutral_item": {"id": 333, "short_name": "fallback"},
                            }
                        ],
                    }
                ],
                snapshot={
                    "match_id": 81,
                    "leagueid": 19543,
                    "players": [{"hero_id": 1, "player_slot": 129}],
                },
            ),
            FakeStratzService(),
            neutral_cache=neutral_cache,
        )

        await pipeline.get_live_tier1_matches()
        result = await pipeline.get_result_match(81, 19543)

        self.assertIsNotNone(result)
        self.assertEqual(result.players[0].neutral_item, {"id": 333, "short_name": "fallback"})

    async def test_neutral_cache_prunes_old_entries(self) -> None:
        neutral_cache = NeutralItemCache(ttl_seconds=10)
        neutral_cache._data = {
            "1": {
                "account:1": {
                    "neutral_item": {"id": 1, "short_name": "old"},
                    "updated_at": int(time.time()) - 60,
                }
            },
            "2": {
                "account:2": {
                    "neutral_item": {"id": 2, "short_name": "fresh"},
                    "updated_at": int(time.time()),
                }
            },
        }

        neutral_cache.prune()

        self.assertNotIn("1", neutral_cache._data)
        self.assertIn("2", neutral_cache._data)

    async def test_neutral_cache_clear_removes_entries(self) -> None:
        neutral_cache = NeutralItemCache()
        neutral_cache._data = {"1": {"account:1": {"neutral_item": {"id": 1}, "updated_at": int(time.time())}}}

        neutral_cache.clear()

        self.assertEqual(neutral_cache._data, {})


class AdapterTests(unittest.TestCase):
    def test_match_adapter_preserves_render_fields(self) -> None:
        match = MatchModel(
            match_id=123,
            league_id=19543,
            league_name="PGL",
            radiant_name="A",
            dire_name="B",
            radiant_score=20,
            dire_score=10,
            radiant_win=True,
            players=[
                PlayerModel(
                    account_id=1,
                    name="Player",
                    hero_id=2,
                    hero_name="Axe",
                    is_radiant=True,
                    kills=1,
                    deaths=2,
                    assists=3,
                    items=[{"id": 50, "short_name": "phase_boots"}],
                    neutral_item={"id": 999, "short_name": "neutral"},
                )
            ],
            bans=[{"hero_id": 1, "is_radiant": True}],
        )

        result = match_to_legacy_dict(match)

        self.assertEqual(result["match_id"], 123)
        self.assertTrue(result["players"][0]["isRadiant"])
        self.assertEqual(result["players"][0]["neutral_item"]["short_name"], "neutral")
        self.assertEqual(result["bans"][0]["hero_id"], 1)

    def test_missing_neutral_players_reports_only_real_players(self) -> None:
        match = MatchModel(
            match_id=123,
            players=[
                PlayerModel(name="Missing", hero_id=1),
                PlayerModel(name="NoHero", hero_id=0),
                PlayerModel(name="Ready", hero_id=2, neutral_item={"id": 1}),
            ],
        )

        self.assertEqual(missing_neutral_players(match), ["Missing"])

    def test_new_neutral_enhancement_ids_are_not_used_as_artifacts(self) -> None:
        player = {
            "item_neutral": 1860,
            "neutral_item_history": [{"item_neutral": "prophets_pendulum", "time": 1200}],
        }

        item = MatchPipelineService._extract_neutral_item(player, {})

        self.assertEqual(item["short_name"], "prophets_pendulum")
