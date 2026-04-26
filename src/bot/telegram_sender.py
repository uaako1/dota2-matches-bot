from __future__ import annotations

import asyncio
import io
import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import NetworkError, RetryAfter, TimedOut

from src.config.settings import settings

logger = logging.getLogger(__name__)


class TelegramSender:
    def __init__(self, token: str | None = None, channel_id: str | None = None, retries: int = 3):
        self.token = token or settings.telegram_token
        self.channel_id = channel_id or settings.channel_id
        self.retries = retries
        self.bot = Bot(token=self.token) if self.token else None

    async def send_photo(self, image: io.BytesIO, caption: str) -> None:
        if not self.bot or not self.channel_id:
            raise RuntimeError("Telegram sender is not configured")
        for attempt in range(1, self.retries + 1):
            try:
                image.seek(0)
                await self.bot.send_photo(
                    chat_id=self.channel_id,
                    photo=image,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                return
            except RetryAfter as exc:
                delay = int(getattr(exc, "retry_after", 5) or 5) + 1
                logger.warning("Telegram flood control. Retry %s/%s in %ss.", attempt, self.retries, delay)
                await asyncio.sleep(delay)
            except (TimedOut, NetworkError) as exc:
                if attempt >= self.retries:
                    raise
                delay = 2 * attempt
                logger.warning("Telegram send failed (%s). Retry %s/%s in %ss.", exc, attempt, self.retries, delay)
                await asyncio.sleep(delay)

        raise RuntimeError("Telegram send failed after retries.")
