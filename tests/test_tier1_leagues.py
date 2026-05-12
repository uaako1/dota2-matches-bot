from __future__ import annotations

import unittest

from config import TIER1_LEAGUES, is_allowed_tier1_league


class Tier1LeagueTests(unittest.TestCase):
    def test_blast_slam_vii_is_configured(self) -> None:
        self.assertEqual(TIER1_LEAGUES[19101], "BLAST Slam VII")

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


if __name__ == "__main__":
    unittest.main()
