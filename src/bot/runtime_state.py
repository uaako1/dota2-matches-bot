from __future__ import annotations

from config import CHANNEL_ID, TELEGRAM_TOKEN
from src.bot.telegram_sender import TelegramSender
from storage import load_state

TELEGRAM_SEND_RETRIES = 3

sender = TelegramSender(token=TELEGRAM_TOKEN, channel_id=CHANNEL_ID, retries=TELEGRAM_SEND_RETRIES)
bot = sender.bot
state = load_state()


def validate_runtime_config() -> list[str]:
    errors = []
    if not TELEGRAM_TOKEN:
        errors.append("Missing TELEGRAM_TOKEN. Set env var or provide telegram_token.txt.")
    if not CHANNEL_ID:
        errors.append("Missing CHANNEL_ID. Set env var or DEFAULT_CHANNEL_ID in config.py.")
    return errors


async def send_photo_with_retry(image_buf, caption: str):
    return await sender.send_photo(image_buf, caption)
