from __future__ import annotations

import unittest
from unittest.mock import patch

import steam_fetcher


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class SteamResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        steam_fetcher._steam_blocked_until = 0
        steam_fetcher._steam_last_status.clear()
        steam_fetcher._live_cache = {"expires_at": 0.0, "games": []}

    def tearDown(self) -> None:
        steam_fetcher._steam_blocked_until = 0
        steam_fetcher._steam_last_status.clear()
        steam_fetcher._live_cache = {"expires_at": 0.0, "games": []}

    def test_steam_429_sets_cooldown_and_skips_next_call(self) -> None:
        responses = [FakeResponse(429, headers={"Retry-After": "60"})]

        def fake_get(*args, **kwargs):
            return responses.pop(0)

        with patch("steam_fetcher.STEAM_API_KEY", "key"), patch("steam_fetcher.shared_http.get", side_effect=fake_get) as mocked_get:
            self.assertEqual(steam_fetcher.get_live_league_games(), [])
            health = steam_fetcher.get_steam_health()
            self.assertTrue(health["blocked"])
            self.assertEqual(health["last_status"]["live"]["status"], 429)
            self.assertEqual(steam_fetcher.get_live_league_games(), [])
            self.assertEqual(mocked_get.call_count, 1)

    def test_steam_success_updates_cache_and_status(self) -> None:
        payload = {"result": {"games": [{"match_id": 123}]}}

        with patch("steam_fetcher.STEAM_API_KEY", "key"), patch("steam_fetcher.shared_http.get", return_value=FakeResponse(200, payload)) as mocked_get:
            self.assertEqual(steam_fetcher.get_live_league_games(), [{"match_id": 123}])
            self.assertEqual(steam_fetcher.get_live_league_games(), [{"match_id": 123}])
            self.assertEqual(mocked_get.call_count, 1)
            self.assertEqual(steam_fetcher.get_steam_health()["last_status"]["live"]["status"], 200)


if __name__ == "__main__":
    unittest.main()
