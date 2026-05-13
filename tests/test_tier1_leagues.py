from __future__ import annotations

import unittest

from config import MIN_PREVIEW_BANS, TIER1_LEAGUES, is_allowed_tier1_league
from src.bot.main import _apply_logo_fallback, _merge_live_neutral_items, _merge_match_summary_metadata
from storage import get_previewed_set, remember_previewed_match


class Tier1LeagueTests(unittest.TestCase):
    def test_blast_slam_vii_is_configured(self) -> None:
        self.assertEqual(TIER1_LEAGUES[19101], "BLAST Slam VII")

    def test_dreamleague_season_29_is_configured(self) -> None:
        self.assertEqual(TIER1_LEAGUES[19696], "DreamLeague Season 29")

    def test_preview_requires_full_ban_phase_by_default(self) -> None:
        self.assertEqual(MIN_PREVIEW_BANS, 14)

    def test_upcoming_main_events_can_be_allowed_by_name(self) -> None:
        self.assertTrue(is_allowed_tier1_league(0, "DreamLeague Season 29"))
        self.assertTrue(is_allowed_tier1_league(0, "BLAST Slam VIII"))
        self.assertTrue(is_allowed_tier1_league(0, "The International 2026"))
        self.assertTrue(is_allowed_tier1_league(0, "Esports World Cup 2026"))
        self.assertTrue(is_allowed_tier1_league(0, "PGL Wallachia Season 9"))
        self.assertTrue(is_allowed_tier1_league(0, "Games of the Future 2026"))

    def test_qualifiers_and_divisions_are_rejected_by_name(self) -> None:
        self.assertFalse(is_allowed_tier1_league(19448, "DreamLeague Season 29: Closed Qualifier"))
        self.assertFalse(is_allowed_tier1_league(0, "DreamLeague Season 15 DPC Western Europe Lower Division"))

    def test_backfill_metadata_prefers_recent_team_data(self) -> None:
        summary = {
            "match_id": 1,
            "radiant_name": "",
            "dire_name": "",
            "radiant_team_id": 0,
            "dire_team_id": 0,
        }
        _merge_match_summary_metadata(
            summary,
            {
                "radiant_name": "PARIVISION",
                "dire_name": "Tundra Esports",
                "radiant_team_id": 9572001,
                "dire_team_id": 8291895,
            },
        )

        self.assertEqual(summary["radiant_name"], "PARIVISION")
        self.assertEqual(summary["dire_name"], "Tundra Esports")
        self.assertEqual(summary["radiant_team_id"], 9572001)
        self.assertEqual(summary["dire_team_id"], 8291895)

    def test_gamerlegion_logo_override_is_available_without_team_lookup(self) -> None:
        details = {"radiant_team": {"id": 9964962, "logo_url": ""}, "dire_team": {"id": 0, "logo_url": ""}}

        _apply_logo_fallback(details, {})

        self.assertIn("13245379764580870318", details["radiant_team"]["logo_url"])

    def test_live_neutral_items_fill_missing_result_neutral(self) -> None:
        details = {
            "players": [
                {
                    "account_id": 1,
                    "hero_id": 2,
                    "isRadiant": True,
                    "neutral_item": None,
                }
            ]
        }
        match_summary = {
            "players": [
                {
                    "account_id": 1,
                    "hero_id": 2,
                    "team": 0,
                    "neutral_item": {"id": 999, "short_name": "test_neutral"},
                }
            ]
        }

        _merge_live_neutral_items(details, match_summary)

        self.assertEqual(details["players"][0]["neutral_item"]["short_name"], "test_neutral")

    def test_previewed_state_tracks_preview_separately_from_results(self) -> None:
        state = {}

        remember_previewed_match(state, 123)

        self.assertEqual(get_previewed_set(state), {123})
        self.assertNotIn("sent_matches", state)


if __name__ == "__main__":
    unittest.main()
