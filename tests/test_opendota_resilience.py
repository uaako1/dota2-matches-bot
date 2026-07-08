from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import opendota_discovery
from src.bot.main import _sort_backfill_story_matches


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class OpenDotaResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state_file = opendota_discovery.STATE_FILE
        opendota_discovery._opendota_blocked_until = 0
        opendota_discovery._opendota_last_status.clear()
        opendota_discovery._persistent_lookup_cache_loaded = False
        opendota_discovery._persistent_lookup_cache = {"teams": {}, "players": {}, "pro_matches": {}, "league_matches": {}}
        opendota_discovery._match_retry_after.clear()
        opendota_discovery.clear_opendota_memory_cache()

    def tearDown(self) -> None:
        opendota_discovery.STATE_FILE = self._original_state_file
        opendota_discovery._persistent_lookup_cache_loaded = False
        opendota_discovery._persistent_lookup_cache = {"teams": {}, "players": {}, "pro_matches": {}, "league_matches": {}}
        opendota_discovery._match_retry_after.clear()
        opendota_discovery.clear_opendota_memory_cache()

    def test_player_info_does_not_cache_429_failure(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            opendota_discovery.STATE_FILE = str(Path(tmp_dir) / "bot_state.json")
            responses = [
                FakeResponse(429, headers={"Retry-After": "60"}),
                FakeResponse(200, {"profile": {"personaname": "Fallback", "name": "ProName", "steamid": "1"}}),
            ]
            calls = []

            def fake_get(url: str, timeout: int):
                calls.append(url)
                return responses.pop(0)

            with patch("opendota_discovery.shared_http.get", side_effect=fake_get):
                self.assertEqual(opendota_discovery.get_player_info(123), {})
                opendota_discovery._opendota_blocked_until = 0
                self.assertEqual(opendota_discovery.get_player_info(123)["name"], "ProName")
                self.assertEqual(opendota_discovery.get_player_info(123)["name"], "ProName")

            self.assertEqual(len(calls), 2)

    def test_player_info_uses_persistent_lookup_cache(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            opendota_discovery.STATE_FILE = str(Path(tmp_dir) / "bot_state.json")
            responses = [
                FakeResponse(200, {"profile": {"personaname": "Cached", "name": "EsportName", "steamid": "1"}}),
            ]

            def fake_get(url: str, timeout: int):
                return responses.pop(0)

            with patch("opendota_discovery.shared_http.get", side_effect=fake_get):
                self.assertEqual(opendota_discovery.get_player_info(456)["name"], "EsportName")

            opendota_discovery._persistent_lookup_cache_loaded = False
            opendota_discovery._persistent_lookup_cache = {"teams": {}, "players": {}, "pro_matches": {}, "league_matches": {}}
            opendota_discovery.clear_opendota_memory_cache()

            with patch("opendota_discovery.shared_http.get") as mocked_get:
                self.assertEqual(opendota_discovery.get_player_info(456)["name"], "EsportName")
                mocked_get.assert_not_called()

    def test_match_404_sets_retry_without_repeated_calls(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            opendota_discovery.STATE_FILE = str(Path(tmp_dir) / "bot_state.json")

            def fake_get(url: str, timeout: int):
                return FakeResponse(404)

            with patch("opendota_discovery.shared_http.get", side_effect=fake_get) as mocked_get:
                self.assertEqual(opendota_discovery.get_match_snapshot(999), {})
                self.assertEqual(opendota_discovery.get_match_snapshot(999), {})
                self.assertEqual(mocked_get.call_count, 1)

    def test_pro_matches_uses_ttl_cache(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            opendota_discovery.STATE_FILE = str(Path(tmp_dir) / "bot_state.json")
            payload = [
                {
                    "match_id": 1,
                    "leagueid": 19696,
                    "league_name": "DreamLeague Season 29",
                    "start_time": 1,
                    "radiant_name": "A",
                    "dire_name": "B",
                }
            ]

            def fake_get(url: str, timeout: int):
                return FakeResponse(200, payload)

            with patch("opendota_discovery.shared_http.get", side_effect=fake_get) as mocked_get:
                first = opendota_discovery.get_recent_pro_matches({19696})
                second = opendota_discovery.get_recent_pro_matches({19696})
                self.assertEqual(first, second)
                self.assertEqual(mocked_get.call_count, 1)

    def test_backfill_story_keeps_maps_grouped_by_series(self) -> None:
        rows = [
            {"match_id": 30, "series_id": 300, "start_time": 300},
            {"match_id": 20, "series_id": 200, "start_time": 220},
            {"match_id": 10, "series_id": 100, "start_time": 100},
            {"match_id": 11, "series_id": 100, "start_time": 200},
            {"match_id": 21, "series_id": 200, "start_time": 320},
        ]

        ordered = _sort_backfill_story_matches(rows)

        self.assertEqual([row["match_id"] for row in ordered], [10, 11, 20, 21, 30])


if __name__ == "__main__":
    unittest.main()
