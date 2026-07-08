from __future__ import annotations

import unittest
from unittest.mock import patch

from config import MIN_PREVIEW_BANS, TIER1_LEAGUES, is_allowed_tier1_league, resolve_tier1_league_name
from src.bot.main import (
    _apply_logo_fallback,
    _build_series_context,
    _merge_recorded_preview_context,
    _merge_live_neutral_items,
    _merge_match_summary_metadata,
    maybe_post_recovery_preview,
)
from storage import get_match_post_record, has_match_posted, get_previewed_set, remember_match_post, remember_previewed_match


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
        self.assertTrue(is_allowed_tier1_league(0, "EWC 2026"))
        self.assertTrue(is_allowed_tier1_league(0, "PGL Wallachia Season 9"))
        self.assertTrue(is_allowed_tier1_league(0, "Games of the Future 2026"))

    def test_current_ewc_league_id_resolves_without_api_name(self) -> None:
        self.assertTrue(is_allowed_tier1_league(19785, ""))
        self.assertEqual(resolve_tier1_league_name(19785, ""), "Esports World Cup 2026")

    def test_dynamic_tier1_league_ids_include_upcoming_name_matches(self) -> None:
        from src.bot.discovery import get_active_tier1_league_ids

        with patch(
            "src.bot.discovery.get_recent_pro_matches",
            return_value=[
                {"match_id": 1, "leagueid": 777001, "league_name": "EWC 2026"},
                {"match_id": 2, "leagueid": 777002, "league_name": "The International 2026"},
                {"match_id": 3, "leagueid": 777003, "league_name": "Random Regional League"},
            ],
        ):
            league_ids = get_active_tier1_league_ids()

        self.assertIn(777001, league_ids)
        self.assertIn(777002, league_ids)
        self.assertNotIn(777003, league_ids)

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

    def test_logo_fallback_uses_generic_team_logo_when_lookup_is_missing(self) -> None:
        details = {"radiant_team": {"id": 1234567, "logo_url": ""}, "dire_team": {"id": 0, "logo_url": ""}}

        with patch("src.bot.main.get_team_info", return_value={}):
            _apply_logo_fallback(details, {})

        self.assertEqual(
            details["radiant_team"]["logo_url"],
            "https://steamcdn-a.akamaihd.net/apps/dota2/images/team_logos/1234567.png",
        )

    def test_current_dreamleague_logo_overrides_cover_common_teams(self) -> None:
        from config import TEAM_LOGO_OVERRIDES

        for team_id in (2163, 7119388, 8255888, 9467224, 9572001, 9964962, 10136357):
            with self.subTest(team_id=team_id):
                self.assertIn(team_id, TEAM_LOGO_OVERRIDES)
                self.assertTrue(TEAM_LOGO_OVERRIDES[team_id].startswith("https://"))

    def test_current_blast_logo_overrides_cover_common_teams(self) -> None:
        from config import TEAM_LOGO_OVERRIDES

        for team_id in (2586976, 8599101, 9303484, 9338413, 9823272, 9824702, 10081680, 10150413, 10150538):
            with self.subTest(team_id=team_id):
                self.assertIn(team_id, TEAM_LOGO_OVERRIDES)
                self.assertTrue(TEAM_LOGO_OVERRIDES[team_id].startswith("https://"))

    def test_resolve_tier1_league_name_ignores_placeholder_numbers(self) -> None:
        self.assertEqual(resolve_tier1_league_name(19422, "19422"), "ESL One Birmingham 2026")
        self.assertEqual(resolve_tier1_league_name(0, "League 191919"), "Pro Match")

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

    def test_series_context_does_not_score_future_maps_when_current_match_is_missing(self) -> None:
        with patch(
            "src.bot.main.get_league_matches",
            return_value=[
                {
                    "match_id": 30,
                    "series_id": 99,
                    "start_time": 100,
                    "radiant_team_id": 5,
                    "dire_team_id": 6,
                    "radiant_win": True,
                },
                {
                    "match_id": 31,
                    "series_id": 99,
                    "start_time": 200,
                    "radiant_team_id": 6,
                    "dire_team_id": 5,
                    "radiant_win": True,
                },
                {
                    "match_id": 32,
                    "series_id": 99,
                    "start_time": 300,
                    "radiant_team_id": 5,
                    "dire_team_id": 6,
                    "radiant_win": False,
                },
            ],
        ):
            context = _build_series_context(
                999,
                19101,
                snapshot={},
                match_summary={"series_id": 99, "radiant_team_id": 5, "dire_team_id": 6},
                include_series_score=True,
            )

        self.assertIsNone(context["game_number"])
        self.assertIsNone(context["series_score"])

    def test_captions_hide_series_score_without_reliable_game_number(self) -> None:
        from formatter import build_preview_caption, build_result_caption

        details = {
            "league_name": "BLAST Slam VII",
            "radiant_name": "Team A",
            "dire_name": "Team B",
            "radiant_score": 30,
            "dire_score": 20,
            "radiant_win": True,
            "duration": 1800,
            "series_score": {"radiant": 2, "dire": 2},
            "best_of": 5,
        }

        preview_caption = build_preview_caption(details)
        result_caption = build_result_caption(details)

        self.assertIn("Team A vs Team B", preview_caption)
        self.assertIn("Team A vs Team B", result_caption)
        self.assertNotIn("[2:2]", preview_caption)
        self.assertNotIn("[2:2]", result_caption)

    def test_previewed_state_tracks_preview_separately_from_results(self) -> None:
        state = {}

        remember_previewed_match(state, 123)

        self.assertEqual(get_previewed_set(state), {123})
        self.assertNotIn("sent_matches", state)

    def test_match_post_ledger_tracks_preview_and_result_separately(self) -> None:
        state = {}
        details = {
            "leagueid": 19696,
            "league_name": "DreamLeague Season 29",
            "series_id": 77,
            "series_type": 1,
            "best_of": 3,
            "game_number": 2,
            "radiant_name": "Team A",
            "dire_name": "Team B",
        }

        remember_match_post(state, 123, "preview", details, message_id=10)

        self.assertTrue(has_match_posted(state, 123, "preview"))
        self.assertFalse(has_match_posted(state, 123, "result"))
        self.assertEqual(get_match_post_record(state, 123)["preview"]["game_number"], 2)

    def test_recorded_preview_context_overrides_result_map_number_after_restart(self) -> None:
        import src.bot.main as main

        previous_state = main.state
        main.state = {}
        try:
            remember_match_post(
                main.state,
                555,
                "preview",
                {
                    "series_id": 99,
                    "series_type": 1,
                    "best_of": 3,
                    "game_number": 2,
                    "radiant_name": "Team A",
                    "dire_name": "Team B",
                },
            )
            details = {"match_id": 555, "series_id": 99, "best_of": 3, "game_number": 1}

            _merge_recorded_preview_context(details, 555)

            self.assertEqual(details["game_number"], 2)
            self.assertEqual(details["series_label"], "BO3")
        finally:
            main.state = previous_state


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
