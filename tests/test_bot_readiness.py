from __future__ import annotations

import unittest

from src.bot.readiness import has_complete_draft, result_asset_gaps, snapshot_has_final_result


class BotReadinessTests(unittest.TestCase):
    def test_snapshot_final_result_requires_winner_duration_and_players(self) -> None:
        self.assertFalse(snapshot_has_final_result({}))
        self.assertFalse(snapshot_has_final_result({"radiant_win": True, "duration": 100}))
        self.assertFalse(snapshot_has_final_result({"radiant_win": None, "duration": 100, "players": [{}]}))
        self.assertTrue(snapshot_has_final_result({"radiant_win": False, "duration": 100, "players": [{}]}))

    def test_complete_draft_requires_five_heroes_per_side(self) -> None:
        details = {
            "players": [
                *({"isRadiant": True, "hero_id": hero_id} for hero_id in range(1, 6)),
                *({"isRadiant": False, "hero_id": hero_id} for hero_id in range(6, 11)),
            ]
        }

        self.assertTrue(has_complete_draft(details))

    def test_result_asset_gaps_require_neutral_after_seven_minutes(self) -> None:
        details = {
            "duration": 8 * 60,
            "players": [
                {"name": "Ready", "hero_name": "Axe", "neutral_item": {"short_name": "arcane_ring"}},
                {"name": "Missing", "hero_name": "Bane"},
            ],
        }

        missing_neutral, _, _ = result_asset_gaps(details)

        self.assertEqual(missing_neutral, ["Missing/Bane"])
