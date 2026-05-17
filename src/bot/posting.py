from __future__ import annotations

import asyncio
import logging

from formatter import build_preview_caption, build_result_caption
from image_generator import generate_match_preview_image, generate_match_result_image
from src.bot.runtime_state import send_photo_with_retry
from storage import (
    forget_live_announcement,
    has_match_posted,
    mark_tracked_live_preview_posted,
    remember_match_post,
    remember_live_announcement,
    remember_previewed_match,
    remember_sent_match,
    remove_tracked_live_match,
    save_state,
)

logger = logging.getLogger(__name__)


async def send_result_post(details: dict, state: dict, *, match_id: int, post_delay_seconds: int) -> None:
    if has_match_posted(state, match_id, "result"):
        logger.info("Skipping duplicate result post for %s; already recorded in state.", match_id)
        remember_sent_match(state, match_id)
        remove_tracked_live_match(state, match_id)
        forget_live_announcement(state, match_id)
        save_state(state)
        return

    image_buf = generate_match_result_image(details)
    caption = build_result_caption(details)
    message = await send_photo_with_retry(image_buf, caption)

    remember_match_post(state, match_id, "result", details, message_id=getattr(message, "message_id", None))
    remember_sent_match(state, match_id)
    save_state(state)

    logger.info("Posted match %s", match_id)
    remove_tracked_live_match(state, match_id)
    forget_live_announcement(state, match_id)
    save_state(state)

    await asyncio.sleep(post_delay_seconds)


async def send_live_preview_post(details: dict, state: dict, *, match_id: int) -> None:
    if has_match_posted(state, match_id, "preview"):
        logger.info("Skipping duplicate live preview for %s; already recorded in state.", match_id)
        remember_live_announcement(state, match_id)
        remember_previewed_match(state, match_id)
        mark_tracked_live_preview_posted(state, match_id)
        save_state(state)
        return

    image_buf = generate_match_preview_image(details)
    caption = build_preview_caption(details)
    message = await send_photo_with_retry(image_buf, caption)
    remember_match_post(state, match_id, "preview", details, message_id=getattr(message, "message_id", None))
    remember_live_announcement(state, match_id)
    remember_previewed_match(state, match_id)
    mark_tracked_live_preview_posted(state, match_id)
    save_state(state)
    logger.info("Posted live preview for %s (bans_source=%s)", match_id, details.get("bans_source") or "unknown")


async def send_historical_preview_post(details: dict, *, match_id: int, post_delay_seconds: int) -> None:
    preview_image = generate_match_preview_image(details)
    preview_caption = build_preview_caption(details)
    await send_photo_with_retry(preview_image, preview_caption)
    logger.info("Posted historical preview for %s", match_id)
    await asyncio.sleep(post_delay_seconds)


async def send_recovery_preview_post(details: dict, state: dict, *, match_id: int, post_delay_seconds: int) -> None:
    await send_historical_preview_post(details, match_id=match_id, post_delay_seconds=post_delay_seconds)
    remember_previewed_match(state, match_id)
    save_state(state)
