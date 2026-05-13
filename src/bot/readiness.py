from __future__ import annotations

import logging

from config import MIN_PREVIEW_BANS
from image_generator import _item_image

logger = logging.getLogger(__name__)


def has_complete_draft(details: dict) -> bool:
    players = details.get("players") or []
    radiant_count = sum(1 for player in players if player.get("isRadiant") and player.get("hero_id"))
    dire_count = sum(1 for player in players if not player.get("isRadiant") and player.get("hero_id"))
    return radiant_count >= 5 and dire_count >= 5


def has_enough_bans(details: dict) -> bool:
    return len(details.get("bans") or []) >= MIN_PREVIEW_BANS


def snapshot_has_final_result(snapshot: dict) -> bool:
    if not snapshot:
        return False
    if snapshot.get("radiant_win") is None:
        return False
    if int(snapshot.get("duration") or 0) <= 0:
        return False
    return bool(snapshot.get("players") or [])


def result_asset_gaps(details: dict) -> tuple[list[str], list[str], list[str]]:
    players = details.get("players") or []
    require_neutral_items = int(details.get("duration") or 0) >= 7 * 60
    missing_neutral = []
    missing_neutral_icon = []
    missing_buff_icon = []
    for player in players:
        player_name = player.get("name") or player.get("hero_name") or "Player"
        hero_name = player.get("hero_name") or ""
        neutral = player.get("neutral_item")
        if neutral:
            if not _item_image(neutral.get("short_name") or ""):
                missing_neutral_icon.append(f"{player_name}/{hero_name}:{neutral.get('short_name') or neutral.get('id')}")
        elif require_neutral_items:
            missing_neutral.append(f"{player_name}/{hero_name}")
        for buff in player.get("buffs") or []:
            if not _item_image(buff.get("short_name") or ""):
                missing_buff_icon.append(f"{player_name}/{hero_name}:{buff.get('short_name') or buff.get('id')}")
    return missing_neutral, missing_neutral_icon, missing_buff_icon


def log_result_asset_quality(match_id: int, details: dict) -> None:
    players = details.get("players") or []
    missing_neutral, missing_neutral_icon, missing_buff_icon = result_asset_gaps(details)
    logger.info(
        "Result assets match %s: players=%s neutral_missing=%s neutral_icon_missing=%s buff_icon_missing=%s",
        match_id,
        len(players),
        len(missing_neutral),
        len(missing_neutral_icon),
        len(missing_buff_icon),
    )
    if missing_neutral or missing_neutral_icon or missing_buff_icon:
        logger.warning(
            "Result asset gaps match %s: neutral_missing=%s neutral_icon_missing=%s buff_icon_missing=%s",
            match_id,
            missing_neutral[:10],
            missing_neutral_icon[:10],
            missing_buff_icon[:10],
        )
