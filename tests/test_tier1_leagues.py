from __future__ import annotations

import unittest
from unittest.mock import patch

from config import MIN_PREVIEW_BANS, TIER1_LEAGUES, is_allowed_tier1_league
from src.bot.main import (
    _apply_logo_fallback,
    _build_series_context,
    _merge_live_neutral_items,
    _merge_match_summary_metadata,
    maybe_post_recovery_preview,
)
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

    def test_series_context_uses_match_summary_when_snapshot_metadata_is_missing(self) -> None:
        with patch(
            "src.bot.main.get_league_matches",
            return_value=[
                {
                    "match_id": 10,
                    "series_id": 77,
                    "start_time": 100,
                    "radiant_team_id": 1,
                    "dire_team_id": 2,
                    "radiant_win": False,
                },
                {
                    "match_id": 11,
                    "series_id": 77,
                    "start_time": 200,
                    "radiant_team_id": 1,
                    "dire_team_id": 2,
                    "radiant_win": True,
                },
            ],
        ):
            context = _build_series_context(
                11,
                None,
                snapshot={},
                match_summary={"leagueid": 19696, "radiant_team_id": 1, "dire_team_id": 2},
                include_series_score=True,
            )

        self.assertEqual(context["best_of"], 3)
        self.assertEqual(context["game_number"], 2)
        self.assertEqual(context["series_score"], {"radiant": 1, "dire": 1})

    def test_series_context_uses_league_row_when_snapshot_and_summary_ids_are_missing(self) -> None:
        with patch(
            "src.bot.main.get_league_matches",
            return_value=[
                {
                    "match_id": 20,
                    "series_id": 88,
                    "start_time": 100,
                    "radiant_team_id": 3,
                    "dire_team_id": 4,
                    "radiant_win": True,
                },
                {
                    "match_id": 21,
                    "series_id": 88,
                    "start_time": 200,
                    "radiant_team_id": 4,
                    "dire_team_id": 3,
                    "radiant_win": True,
                },
            ],
        ):
            context = _build_series_context(
                21,
                19696,
                snapshot={},
                match_summary={},
                include_series_score=True,
            )

        self.assertEqual(context["best_of"], 3)
        self.assertEqual(context["game_number"], 2)
        self.assertEqual(context["series_score"], {"radiant": 1, "dire": 1})

    def test_previewed_state_tracks_preview_separately_from_results(self) -> None:
        state = {}

        remember_previewed_match(state, 123)

        self.assertEqual(get_previewed_set(state), {123})
        self.assertNotIn("sent_matches", state)


class RecoveryPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_preview_does_not_duplicate_announced_live_preview(self) -> None:
        import src.bot.main as main

        previous_state = main.state
        main.state = {
            "announced_live_matches": [123],
            "previewed_matches": [],
            "tracked_live_matches": {},
        }
        try:
            await maybe_post_recovery_preview({"match_id": 123})
        finally:
            state = main.state
            main.state = previous_state

        self.assertEqual(get_previewed_set(state), {123})


if __name__ == "__main__":
    unittest.main()
