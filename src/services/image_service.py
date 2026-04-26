from __future__ import annotations

import asyncio
import io


class ImageService:
    def __init__(self, preview_renderer=None, result_renderer=None) -> None:
        self._preview_renderer = preview_renderer
        self._result_renderer = result_renderer

    async def generate_preview_image(self, match: dict) -> io.BytesIO:
        renderer = self._preview_renderer
        if renderer is None:
            from image_generator import generate_match_preview_image

            renderer = generate_match_preview_image

        return await asyncio.to_thread(renderer, match)

    async def generate_result_image(self, match: dict) -> io.BytesIO:
        renderer = self._result_renderer
        if renderer is None:
            from image_generator import generate_match_result_image

            renderer = generate_match_result_image

        return await asyncio.to_thread(renderer, match)
