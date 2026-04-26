from __future__ import annotations

import io

from telegram import Bot
from telegram.constants import ParseMode

from src.config.settings import settings


class TelegramSender:
    def __init__(self, token: str | None = None, channel_id: str | None = None):
        self.token = token or settings.telegram_token
        self.channel_id = channel_id or settings.channel_id
        self.bot = Bot(token=self.token) if self.token else None

    async def send_photo(self, image: io.BytesIO, caption: str) -> None:
        if not self.bot or not self.channel_id:
            raise RuntimeError("Telegram sender is not configured")
        image.seek(0)
        await self.bot.send_photo(
            chat_id=self.channel_id,
            photo=image,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
