from __future__ import annotations

import io
import unittest

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
