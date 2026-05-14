from __future__ import annotations

import unittest
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
        opendota_discovery._opendota_blocked_until = 0
        opendota_discovery._opendota_last_status.clear()
        opendota_discovery.clear_opendota_memory_cache()

    def test_player_info_does_not_cache_429_failure(self) -> None:
        responses = [
            FakeResponse(429, headers={"Retry-After": "60"}),
            FakeResponse(200, {"profile": {"personaname": "Fallback", "name": "ProName", "steamid": "1"}}),
        ]
        calls = []

        def fake_get(url: str, timeout: int):
            calls.append(url)
            return responses.pop(0)

        with patch("opendota_discovery.requests.get", side_effect=fake_get):
            self.assertEqual(opendota_discovery.get_player_info(123), {})
            opendota_discovery._opendota_blocked_until = 0
            self.assertEqual(opendota_discovery.get_player_info(123)["name"], "ProName")
            self.assertEqual(opendota_discovery.get_player_info(123)["name"], "ProName")

        self.assertEqual(len(calls), 2)

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
