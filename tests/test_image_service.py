from __future__ import annotations

import io
import unittest

from PIL import Image

from image_generator import generate_match_result_image
from src.services.image_service import ImageService


class ImageServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_wrapper_returns_bytes_io(self) -> None:
        service = ImageService(preview_renderer=lambda match: io.BytesIO(b"x"))
        result = await service.generate_preview_image({"match_id": 1})
        self.assertIsInstance(result, io.BytesIO)

    async def test_result_wrapper_returns_bytes_io(self) -> None:
        service = ImageService(result_renderer=lambda match: io.BytesIO(b"y"))
        result = await service.generate_result_image({"match_id": 2})
        self.assertIsInstance(result, io.BytesIO)


class ResultImageRenderTests(unittest.TestCase):
    def test_result_image_renders_16_9_with_lh_denies(self) -> None:
        players = []
        for idx in range(10):
            players.append(
                {
                    "isRadiant": idx < 5,
                    "hero_name": f"Hero {idx + 1}",
                    "hero_short_name": "",
                    "name": f"Player{idx + 1}",
                    "kills": idx,
                    "deaths": idx // 2,
                    "assists": idx + 3,
                    "last_hits": 100 + idx,
                    "denies": idx,
                    "gold_per_min": 400 + idx,
                    "xp_per_min": 500 + idx,
                    "net_worth": 12000 + idx,
                    "hero_damage": 10000 + idx,
                    "hero_healing": 0,
                    "tower_damage": 0,
                    "items": [],
                    "backpack": [],
                    "buffs": [],
                }
            )
        image = generate_match_result_image(
            {
                "league_name": "The International 2026",
                "radiant_name": "Team Spirit",
                "dire_name": "Team Liquid",
                "radiant_score": 32,
                "dire_score": 21,
                "radiant_win": True,
                "duration": 2145,
                "game_number": 2,
                "players": players,
                "radiant_team": {},
                "dire_team": {},
            }
        )
        with Image.open(image) as rendered:
            self.assertEqual(rendered.size, (1920, 1080))
