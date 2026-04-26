import argparse
import asyncio
import logging

from config import CHECK_INTERVAL_MINUTES
from config import LIVE_ANNOUNCE_ENABLED, LIVE_CHECK_ENABLED, MAX_MATCHES_PER_CHECK, POST_DELAY_SECONDS
from config import TIER1_LEAGUES
from opendota_discovery import get_league_matches, get_match_snapshot, get_player_info, get_team_info
from src.bot.discovery import (
    filter_current_live_matches,
    get_finished_tracked_matches,
    get_live_configured_matches,
    get_raw_configured_live_rows,
    get_recent_configured_matches,
    get_recent_finished_safety_matches,
    get_recently_deactivated_matches,
)
from src.bot.posting import send_historical_preview_post, send_live_preview_post, send_result_post
from src.bot.readiness import (
    MIN_PREVIEW_BANS,
    has_complete_draft,
    has_enough_bans,
    log_result_asset_quality,
    result_asset_gaps,
)
from src.bot.runtime_state import bot, state, validate_runtime_config
from src.bot.scheduler import run_interval_scheduler
from steam_fetcher import get_live_league_game
from storage import (
    get_announced_live_set,
    get_cached_draft,
    get_sent_set,
    remember_draft_cache,
    save_state,
    upsert_tracked_live_match,
)
from stratz_fetcher import (
    get_item_map,
    get_hero_map,
    get_match_details,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

def _apply_logo_fallback(details: dict, match_summary: dict | None = None) -> dict:
    match_summary = match_summary or {}
    radiant_team = details.setdefault("radiant_team", {})
    dire_team = details.setdefault("dire_team", {})

    radiant_id = int(radiant_team.get("id") or match_summary.get("radiant_team_id") or 0)
    dire_id = int(dire_team.get("id") or match_summary.get("dire_team_id") or 0)
    if radiant_id:
        radiant_info = get_team_info(radiant_id)
        radiant_team["id"] = radiant_id
        radiant_team["logo_url"] = radiant_info.get("logo_url") or radiant_team.get("logo_url") or ""
    if not radiant_team.get("logo_url"):
        radiant_logo_id = str(match_summary.get("radiant_logo_id") or match_summary.get("team_logo_radiant") or "").strip()
        if radiant_logo_id:
            radiant_team["logo_url"] = f"https://steamusercontent-a.akamaihd.net/ugc/{radiant_logo_id}/"
    if dire_id:
        dire_info = get_team_info(dire_id)
        dire_team["id"] = dire_id
        dire_team["logo_url"] = dire_info.get("logo_url") or dire_team.get("logo_url") or ""
    if not dire_team.get("logo_url"):
        dire_logo_id = str(match_summary.get("dire_logo_id") or match_summary.get("team_logo_dire") or "").strip()
        if dire_logo_id:
            dire_team["logo_url"] = f"https://steamusercontent-a.akamaihd.net/ugc/{dire_logo_id}/"
    return details


def _preferred_player_name(account_id: int, fallback_name: str = "Player") -> str:
    info = get_player_info(int(account_id or 0))
    return (info.get("name") or info.get("personaname") or fallback_name or "Player").strip()


def _series_best_of(series_type: int | None) -> int | None:
    mapping = {0: 1, 1: 3, 2: 5}
    return mapping.get(int(series_type)) if series_type is not None else None


def _build_series_context(
    match_id: int,
    league_id: int | None,
    snapshot: dict | None = None,
    include_series_score: bool = False,
    include_current_match_in_score: bool = True,
) -> dict:
    snapshot = snapshot or {}
    series_id = int(snapshot.get("series_id") or 0)
    series_type = snapshot.get("series_type")
    if not series_id:
        return {}

    best_of = _series_best_of(series_type)
    resolved_league_id = int(league_id or snapshot.get("leagueid") or 0)

    def load_series_matches() -> list[dict]:
        rows = get_league_matches(resolved_league_id)
        matches = [row for row in rows if int(row.get("series_id") or 0) == series_id]
        matches.sort(key=lambda row: int(row.get("start_time") or 0))
        return matches

    series_matches = load_series_matches()

    game_number = None
    series_score = None
    current_index = None
    if series_matches:
        for index, row in enumerate(series_matches, start=1):
            if int(row.get("match_id") or 0) == int(match_id):
                game_number = index
                current_index = index
                break

        if include_series_score:
            team_wins: dict[int, int] = {}
            if current_index:
                score_until = current_index if include_current_match_in_score else max(current_index - 1, 0)
                scored_matches = series_matches[:score_until]
            else:
                scored_matches = series_matches
            for row in scored_matches:
                radiant_team_id = int(row.get("radiant_team_id") or 0)
                dire_team_id = int(row.get("dire_team_id") or 0)
                radiant_win = bool(row.get("radiant_win"))
                winner_id = radiant_team_id if radiant_win else dire_team_id
                if winner_id:
                    team_wins[winner_id] = team_wins.get(winner_id, 0) + 1

            radiant_team_id = int(snapshot.get("radiant_team_id") or 0)
            dire_team_id = int(snapshot.get("dire_team_id") or 0)
            if radiant_team_id or dire_team_id:
                series_score = {
                    "radiant": team_wins.get(radiant_team_id, 0),
                    "dire": team_wins.get(dire_team_id, 0),
                }

    label = None
    if best_of:
        label = f"BO{best_of}"
    is_grand_final = bool(best_of == 5)

    return {
        "series_id": series_id,
        "series_type": int(series_type) if series_type is not None else None,
        "best_of": best_of,
        "series_label": label,
        "game_number": game_number,
        "series_score": series_score,
        "is_grand_final": is_grand_final,
    }


def _build_steam_series_context(steam_live: dict) -> dict:
    if not steam_live:
        return {}

    best_of = _series_best_of(steam_live.get("series_type"))
    radiant_wins = int(steam_live.get("radiant_series_wins") or 0)
    dire_wins = int(steam_live.get("dire_series_wins") or 0)
    total_finished_maps = radiant_wins + dire_wins

    return {
        "series_type": int(steam_live.get("series_type")) if steam_live.get("series_type") is not None else None,
        "best_of": best_of,
        "series_label": f"BO{best_of}" if best_of else None,
        "game_number": total_finished_maps + 1 if best_of else None,
        "series_score": {"radiant": radiant_wins, "dire": dire_wins} if total_finished_maps > 0 else None,
        "is_grand_final": bool(best_of == 5),
    }


def _infer_game_number_from_score(series_score: dict | None, include_current_map: bool) -> int | None:
    series_score = series_score or {}
    radiant_wins = int(series_score.get("radiant") or 0)
    dire_wins = int(series_score.get("dire") or 0)
    total_maps = radiant_wins + dire_wins
    if total_maps <= 0:
        return None
    return total_maps if include_current_map else total_maps + 1


def _merge_series_context(target: dict, context: dict, *, include_current_map: bool) -> dict:
    for key, value in (context or {}).items():
        if value is None:
            continue
        if key == "series_score":
            if value:
                target[key] = value
            continue
        if key == "game_number":
            if value:
                target[key] = value
            continue
        if key not in target or target.get(key) in (None, "", 0, False):
            target[key] = value

    if not target.get("game_number"):
        inferred = _infer_game_number_from_score(target.get("series_score"), include_current_map=include_current_map)
        if inferred:
            target["game_number"] = inferred
    return target


def _apply_official_snapshot_result(details: dict, snapshot: dict, match_summary: dict | None = None) -> dict:
    match_summary = match_summary or {}
    if not snapshot:
        return details

    for key in ("radiant_score", "dire_score", "duration"):
        if snapshot.get(key) is not None:
            details[key] = int(snapshot.get(key) or 0)

    if snapshot.get("radiant_win") is not None:
        details["radiant_win"] = bool(snapshot.get("radiant_win"))

    if snapshot.get("radiant_name"):
        details["radiant_name"] = snapshot.get("radiant_name")
    elif match_summary.get("radiant_name"):
        details["radiant_name"] = match_summary.get("radiant_name")

    if snapshot.get("dire_name"):
        details["dire_name"] = snapshot.get("dire_name")
    elif match_summary.get("dire_name"):
        details["dire_name"] = match_summary.get("dire_name")

    if snapshot.get("leagueid"):
        details["leagueid"] = int(snapshot.get("leagueid") or details.get("leagueid") or 0)

    radiant_team_id = int(snapshot.get("radiant_team_id") or match_summary.get("radiant_team_id") or 0)
    dire_team_id = int(snapshot.get("dire_team_id") or match_summary.get("dire_team_id") or 0)
    if radiant_team_id:
        details.setdefault("radiant_team", {})["id"] = radiant_team_id
    if dire_team_id:
        details.setdefault("dire_team", {})["id"] = dire_team_id

    return details


def _snapshot_item_entry(item_id: int | str | None, item_map: dict[int, dict]) -> dict | None:
    try:
        resolved_id = int(item_id or 0)
    except (TypeError, ValueError):
        resolved_id = 0
    item = item_map.get(resolved_id)
    if not item:
        return None
    return {
        "id": int(item["id"]),
        "short_name": item.get("short_name") or "",
        "display_name": item.get("display_name") or "",
    }


def _snapshot_neutral_item_entry(payload: dict, item_map: dict[int, dict]) -> dict | None:
    for entry in reversed(payload.get("neutral_item_history") or []):
        short_name = entry.get("item_neutral")
        if short_name:
            return {
                "id": 0,
                "short_name": str(short_name),
                "display_name": str(short_name).replace("_", " ").title(),
            }

    enhancement_ids = set(range(1583, 1597)) | set(range(1856, 1874))
    for key in ("item_neutral", "item_neutral_id", "neutral0Id", "neutral0_id", "neutral_item", "neutralItem", "item_neutral2"):
        try:
            raw_id = int(payload.get(key) or 0)
        except (TypeError, ValueError):
            raw_id = 0
        if raw_id in enhancement_ids:
            continue
        item = _snapshot_item_entry(payload.get(key), item_map)
        if item:
            return item
    return None


def _snapshot_buff_items(player: dict, item_map: dict[int, dict]) -> list[dict]:
    buffs = []
    if int(player.get("aghanims_scepter") or 0):
        item = _snapshot_item_entry(108, item_map)
        if item:
            buffs.append(item)
    if int(player.get("aghanims_shard") or 0):
        item = _snapshot_item_entry(609, item_map)
        if item:
            buffs.append(item)
    if int(player.get("moonshard") or 0):
        item = _snapshot_item_entry(247, item_map)
        if item:
            buffs.append(item)
    return buffs


def _merge_snapshot_player_loadouts(details: dict, snapshot: dict) -> dict:
    snapshot_players = snapshot.get("players") or []
    detail_players = details.get("players") or []
    if not snapshot_players or not detail_players:
        return details

    item_map = get_item_map()
    snapshot_by_hero_side = {
        (bool(player.get("isRadiant")), int(player.get("hero_id") or 0)): player
        for player in snapshot_players
        if player.get("hero_id")
    }

    for player in detail_players:
        source = snapshot_by_hero_side.get((bool(player.get("isRadiant")), int(player.get("hero_id") or 0)))
        if not source:
            continue

        if not player.get("neutral_item"):
            neutral = _snapshot_neutral_item_entry(source, item_map)
            if neutral:
                player["neutral_item"] = neutral

        if not player.get("items"):
            items = [_snapshot_item_entry(source.get(f"item_{slot}"), item_map) for slot in range(6)]
            player["items"] = [item for item in items if item]

        if not player.get("backpack"):
            backpack = [_snapshot_item_entry(source.get(f"backpack_{slot}"), item_map) for slot in range(3)]
            player["backpack"] = [item for item in backpack if item]

        if not player.get("buffs"):
            player["buffs"] = _snapshot_buff_items(source, item_map)

    return details


def _build_preview_details(match_summary: dict) -> dict:
    match_id = int(match_summary["match_id"])
    hero_map = get_hero_map()
    snapshot = get_match_snapshot(match_id)
    steam_live = get_live_league_game(match_id)
    stratz_live = None

    live_names = {}
    live_players = []
    for player in match_summary.get("players") or []:
        account_id = int(player.get("account_id") or 0)
        hero_id = int(player.get("hero_id") or 0)
        hero = hero_map.get(hero_id, {})
        is_radiant = int(player.get("team") or 0) == 0
        name = _preferred_player_name(account_id, player.get("name") or player.get("personaname") or "Player")
        live_names[account_id] = name
        live_players.append(
            {
                "account_id": account_id,
                "team_slot": int(player.get("team_slot") or 0),
                "isRadiant": is_radiant,
                "hero_id": hero_id,
                "hero_name": hero.get("display_name") or "",
                "hero_short_name": hero.get("short_name") or "",
                "name": name,
            }
        )

    snapshot_players = snapshot.get("players") or []
    player_by_team_hero = {
        (bool(player.get("isRadiant")), int(player.get("hero_id") or 0)): player
        for player in snapshot_players
        if player.get("hero_id")
    }
    for player in live_players:
        source = player_by_team_hero.get((player["isRadiant"], player["hero_id"])) or {}
        if source.get("personaname"):
            source_account_id = int(source.get("account_id") or 0)
            player["name"] = live_names.get(source_account_id) or _preferred_player_name(source_account_id, source.get("personaname") or player["name"])

    if not live_players and snapshot_players:
        for player in snapshot_players:
            hero_id = int(player.get("hero_id") or 0)
            hero = hero_map.get(hero_id, {})
            live_players.append(
                {
                    "account_id": int(player.get("account_id") or 0),
                    "team_slot": int(player.get("team_slot") or 0),
                    "isRadiant": bool(player.get("isRadiant")),
                    "hero_id": hero_id,
                    "hero_name": hero.get("display_name") or "",
                    "hero_short_name": hero.get("short_name") or "",
                    "name": _preferred_player_name(int(player.get("account_id") or 0), player.get("personaname") or "Player"),
                }
            )

    if (not live_players or not snapshot.get("picks_bans")):
        stratz_live = get_match_details(match_id, league_name_override=match_summary.get("league_name")) or {}
        if not live_players and stratz_live.get("players"):
            for player in stratz_live.get("players") or []:
                live_players.append(
                    {
                        "account_id": int(player.get("account_id") or 0),
                        "team_slot": int(player.get("team_slot") or player.get("index") or 0),
                        "isRadiant": bool(player.get("isRadiant")),
                        "hero_id": int(player.get("hero_id") or 0),
                        "hero_name": player.get("hero_name") or "",
                        "hero_short_name": player.get("hero_short_name") or "",
                        "name": player.get("name") or "Player",
                    }
                )

    live_players.sort(key=lambda item: (0 if item["isRadiant"] else 1, item["team_slot"]))

    bans = []
    bans_source = ""
    for entry in sorted(snapshot.get("picks_bans") or [], key=lambda item: int(item.get("order") or 0)):
        if entry.get("is_pick"):
            continue
        hero_id = int(entry.get("hero_id") or 0)
        hero = hero_map.get(hero_id, {})
        bans.append(
            {
                "order": int(entry.get("order") or 0),
                "is_radiant": int(entry.get("team") or 0) == 0,
                "hero_id": hero_id,
                "hero_name": hero.get("display_name") or "",
                "hero_short_name": hero.get("short_name") or "",
            }
        )
    if bans:
        bans_source = "opendota_snapshot"
    if not bans:
        for entry in (stratz_live or {}).get("bans") or []:
            hero_id = int(entry.get("hero_id") or 0)
            hero = hero_map.get(hero_id, {})
            bans.append(
                {
                    "order": int(entry.get("order") or 0),
                    "is_radiant": bool(entry.get("is_radiant")),
                    "hero_id": hero_id,
                    "hero_name": hero.get("display_name") or entry.get("hero_name") or "",
                    "hero_short_name": hero.get("short_name") or entry.get("hero_short_name") or "",
                }
            )
        if bans:
            bans_source = "stratz"
    if not bans:
        for entry in sorted(steam_live.get("picks_bans") or [], key=lambda item: int(item.get("order") or 0)):
            is_pick = bool(entry.get("is_pick") if "is_pick" in entry else entry.get("isPick"))
            if is_pick:
                continue
            hero_id = int(entry.get("hero_id") or entry.get("heroId") or entry.get("bannedHeroId") or 0)
            hero = hero_map.get(hero_id, {})
            if entry.get("team") is not None:
                is_radiant = int(entry.get("team") or 0) == 0
            else:
                is_radiant = bool(entry.get("isRadiant"))
            bans.append(
                {
                    "order": int(entry.get("order") or 0),
                    "is_radiant": is_radiant,
                    "hero_id": hero_id,
                    "hero_name": hero.get("display_name") or "",
                    "hero_short_name": hero.get("short_name") or "",
                }
            )
        if bans:
            bans_source = "steam_picks_bans"
    if not bans:
        scoreboard = steam_live.get("scoreboard") or {}
        order = 0
        for side_key, is_radiant in (("radiant", True), ("dire", False)):
            for entry in ((scoreboard.get(side_key) or {}).get("bans") or []):
                hero_id = int(entry.get("hero_id") or entry.get("heroId") or 0)
                if not hero_id:
                    continue
                hero = hero_map.get(hero_id, {})
                bans.append(
                    {
                        "order": order,
                        "is_radiant": is_radiant,
                        "hero_id": hero_id,
                        "hero_name": hero.get("display_name") or "",
                        "hero_short_name": hero.get("short_name") or "",
                    }
                )
                order += 1
        if bans:
            bans_source = "steam_scoreboard"

    cached_draft = get_cached_draft(state, match_id)
    cached_players = cached_draft.get("players") if isinstance(cached_draft.get("players"), list) else []
    cached_bans = cached_draft.get("bans") if isinstance(cached_draft.get("bans"), list) else []
    if len(cached_players) > len(live_players):
        live_players = cached_players
    if len(cached_bans) > len(bans):
        bans = cached_bans
        bans_source = cached_draft.get("bans_source") or "draft_cache"

    if len(live_players) >= 10 or bans:
        remember_draft_cache(state, match_id, live_players, bans, bans_source)
        save_state(state)

    league_name = (
        match_summary.get("league_name")
        or snapshot.get("league_name")
        or TIER1_LEAGUES.get(int(match_summary.get("leagueid") or match_summary.get("league_id") or snapshot.get("leagueid") or 0))
        or f"League {int(match_summary.get('leagueid') or match_summary.get('league_id') or snapshot.get('leagueid') or 0)}"
    )

    details = {
        "match_id": match_id,
        "league_name": league_name,
        "leagueid": match_summary.get("leagueid") or match_summary.get("league_id") or snapshot.get("leagueid"),
        "radiant_name": snapshot.get("radiant_name") or match_summary.get("radiant_name") or (snapshot.get("radiant_team") or {}).get("name") or "Radiant",
        "dire_name": snapshot.get("dire_name") or match_summary.get("dire_name") or (snapshot.get("dire_team") or {}).get("name") or "Dire",
        "radiant_score": int(match_summary.get("radiant_score") or snapshot.get("radiant_score") or 0),
        "dire_score": int(match_summary.get("dire_score") or snapshot.get("dire_score") or 0),
        "duration": int(match_summary.get("game_time") or snapshot.get("duration") or 0),
        "game_time": int(match_summary.get("game_time") or snapshot.get("duration") or 0),
        "players": live_players,
        "bans": bans,
        "bans_source": bans_source,
        "radiant_team": {"id": int(snapshot.get("radiant_team_id") or match_summary.get("radiant_team_id") or 0), "logo_url": ""},
        "dire_team": {"id": int(snapshot.get("dire_team_id") or match_summary.get("dire_team_id") or 0), "logo_url": ""},
    }
    series_context = _build_series_context(
        match_id,
        details.get("leagueid"),
        snapshot,
        include_series_score=True,
        include_current_match_in_score=False,
    )
    steam_series_context = _build_steam_series_context(steam_live)
    merged_series_context = dict(series_context)
    for key, value in steam_series_context.items():
        if value is not None and not merged_series_context.get(key):
            merged_series_context[key] = value
    _merge_series_context(details, merged_series_context, include_current_map=False)
    return _apply_logo_fallback(details, match_summary)


def _build_result_details_from_snapshot(match_summary: dict) -> dict | None:
    match_id = int(match_summary["match_id"])
    snapshot = get_match_snapshot(match_id)
    if not snapshot or not (snapshot.get("players") or []):
        return None

    hero_map = get_hero_map()
    item_map = get_item_map()

    def item_entry(item_id: int | None):
        item = item_map.get(int(item_id or 0))
        if not item:
            return None
        return {
            "id": int(item["id"]),
            "short_name": item.get("short_name") or "",
            "display_name": item.get("display_name") or "",
        }

    def unit_items(unit: dict):
        items = []
        for slot in range(6):
            items.append(item_entry(unit.get(f"item_{slot}") or unit.get(f"item{slot}")))
        backpack = []
        for slot in range(3):
            backpack.append(item_entry(unit.get(f"backpack_{slot}") or unit.get(f"backpack{slot}")))
        return {
            "unit_name": unit.get("unitname") or unit.get("unit_name") or "",
            "items": [item for item in items if item],
            "backpack": [item for item in backpack if item],
            "neutral_item": _snapshot_neutral_item_entry(unit, item_map),
            "buffs": [],
        }

    players = []
    for player in snapshot.get("players") or []:
        hero_id = int(player.get("hero_id") or 0)
        hero = hero_map.get(hero_id, {})
        items = [item_entry(player.get(f"item_{slot}")) for slot in range(6)]
        backpack = [item_entry(player.get(f"backpack_{slot}")) for slot in range(3)]
        players.append(
            {
                "isRadiant": bool(player.get("isRadiant")),
                "hero_id": hero_id,
                "hero_name": hero.get("display_name") or "",
                "hero_short_name": hero.get("short_name") or "",
                "kills": int(player.get("kills") or 0),
                "deaths": int(player.get("deaths") or 0),
                "assists": int(player.get("assists") or 0),
                "gold_per_min": int(player.get("gold_per_min") or 0),
                "xp_per_min": int(player.get("xp_per_min") or 0),
                "net_worth": int(player.get("net_worth") or 0),
                "hero_damage": int(player.get("hero_damage") or 0),
                "hero_healing": int(player.get("hero_healing") or 0),
                "tower_damage": int(player.get("tower_damage") or 0),
                "name": _preferred_player_name(int(player.get("account_id") or 0), player.get("personaname") or "Player"),
                "items": [item for item in items if item],
                "backpack": [item for item in backpack if item],
                "neutral_item": _snapshot_neutral_item_entry(player, item_map),
                "buffs": _snapshot_buff_items(player, item_map),
                "additional_units": [unit_items(unit) for unit in player.get("additional_units") or []],
            }
        )

    league_id = int(match_summary.get("leagueid") or match_summary.get("league_id") or snapshot.get("leagueid") or 0)
    details = {
        "match_id": match_id,
        "leagueid": league_id,
        "league_name": (
            match_summary.get("league_name")
            or snapshot.get("league_name")
            or TIER1_LEAGUES.get(league_id)
            or f"League {league_id}"
        ),
        "radiant_name": snapshot.get("radiant_name") or match_summary.get("radiant_name") or "Radiant",
        "dire_name": snapshot.get("dire_name") or match_summary.get("dire_name") or "Dire",
        "radiant_score": int(snapshot.get("radiant_score") or match_summary.get("radiant_score") or 0),
        "dire_score": int(snapshot.get("dire_score") or match_summary.get("dire_score") or 0),
        "radiant_win": snapshot.get("radiant_win"),
        "duration": int(snapshot.get("duration") or 0),
        "players": players,
        "radiant_team": {"id": int(snapshot.get("radiant_team_id") or match_summary.get("radiant_team_id") or 0), "logo_url": ""},
        "dire_team": {"id": int(snapshot.get("dire_team_id") or match_summary.get("dire_team_id") or 0), "logo_url": ""},
    }
    _merge_series_context(
        details,
        _build_series_context(match_id, league_id, snapshot, include_series_score=True),
        include_current_map=True,
    )
    return _apply_logo_fallback(details, match_summary)


def _build_historical_preview_details(match_summary: dict) -> dict | None:
    match_id = int(match_summary["match_id"])
    snapshot = get_match_snapshot(match_id)
    if not snapshot or not (snapshot.get("players") or []):
        return None

    hero_map = get_hero_map()
    players = []
    for player in snapshot.get("players") or []:
        hero_id = int(player.get("hero_id") or 0)
        hero = hero_map.get(hero_id, {})
        players.append(
            {
                "account_id": int(player.get("account_id") or 0),
                "team_slot": int(player.get("team_slot") or 0),
                "isRadiant": bool(player.get("isRadiant")),
                "hero_id": hero_id,
                "hero_name": hero.get("display_name") or "",
                "hero_short_name": hero.get("short_name") or "",
                "name": _preferred_player_name(int(player.get("account_id") or 0), player.get("personaname") or "Player"),
            }
        )
    players.sort(key=lambda item: (0 if item.get("isRadiant") else 1, int(item.get("team_slot") or 0)))

    bans = []
    for entry in sorted(snapshot.get("picks_bans") or [], key=lambda item: int(item.get("order") or 0)):
        if entry.get("is_pick"):
            continue
        hero_id = int(entry.get("hero_id") or 0)
        hero = hero_map.get(hero_id, {})
        bans.append(
            {
                "order": int(entry.get("order") or 0),
                "is_radiant": int(entry.get("team") or 0) == 0,
                "hero_id": hero_id,
                "hero_name": hero.get("display_name") or "",
                "hero_short_name": hero.get("short_name") or "",
            }
        )

    league_id = int(match_summary.get("leagueid") or match_summary.get("league_id") or snapshot.get("leagueid") or 0)
    details = {
        "match_id": match_id,
        "leagueid": league_id,
        "league_name": (
            match_summary.get("league_name")
            or snapshot.get("league_name")
            or TIER1_LEAGUES.get(league_id)
            or f"League {league_id}"
        ),
        "radiant_name": snapshot.get("radiant_name") or match_summary.get("radiant_name") or "Radiant",
        "dire_name": snapshot.get("dire_name") or match_summary.get("dire_name") or "Dire",
        "radiant_score": 0,
        "dire_score": 0,
        "duration": 0,
        "game_time": 0,
        "players": players,
        "bans": bans,
        "bans_source": "opendota_snapshot",
        "radiant_team": {"id": int(snapshot.get("radiant_team_id") or match_summary.get("radiant_team_id") or 0), "logo_url": ""},
        "dire_team": {"id": int(snapshot.get("dire_team_id") or match_summary.get("dire_team_id") or 0), "logo_url": ""},
    }
    _merge_series_context(
        details,
        _build_series_context(
            match_id,
            league_id,
            snapshot,
            include_series_score=True,
            include_current_match_in_score=False,
        ),
        include_current_map=False,
    )
    return _apply_logo_fallback(details, match_summary)


async def post_match(match_summary: dict) -> None:
    match_id = int(match_summary["match_id"])
    snapshot = get_match_snapshot(match_id)
    details = _build_result_details_from_snapshot(match_summary)

    if not details:
        logger.warning("Could not build OpenDota snapshot result for match %s, trying STRATZ details.", match_id)
        details = get_match_details(match_id, league_name_override=match_summary.get("league_name"))
    if not details:
        return

    details["league_name"] = (
        details.get("league_name")
        or match_summary.get("league_name")
        or TIER1_LEAGUES.get(int(match_summary.get("leagueid") or match_summary.get("league_id") or 0))
        or f"League {int(match_summary.get('leagueid') or match_summary.get('league_id') or 0)}"
    )
    details.setdefault("leagueid", match_summary.get("leagueid") or match_summary.get("league_id"))
    _apply_official_snapshot_result(details, snapshot, match_summary)
    _merge_series_context(
        details,
        _build_series_context(match_id, details.get("leagueid"), snapshot, include_series_score=True),
        include_current_map=True,
    )
    _merge_snapshot_player_loadouts(details, snapshot)
    _apply_logo_fallback(details, match_summary)
    log_result_asset_quality(match_id, details)
    missing_neutral, missing_neutral_icon, _ = result_asset_gaps(details)
    if missing_neutral or missing_neutral_icon:
        logger.warning(
            "Deferring result post %s because required result assets are incomplete: neutral_missing=%s neutral_icon_missing=%s",
            match_id,
            missing_neutral[:10],
            missing_neutral_icon[:10],
        )
        return

    try:
        await send_result_post(details, state, match_id=match_id, post_delay_seconds=POST_DELAY_SECONDS)
    except Exception as exc:
        logger.error("Failed to post match %s: %s", match_id, exc)


async def post_live_preview(match_summary: dict) -> None:
    match_id = int(match_summary["match_id"])
    details = _build_preview_details(match_summary)
    if not has_complete_draft(details):
        logger.info("Skipping live preview for %s until all 10 picked heroes are available.", match_id)
        return
    if not has_enough_bans(details):
        logger.info(
            "Skipping live preview for %s until bans are available (%s/%s, source=%s).",
            match_id,
            len(details.get("bans") or []),
            MIN_PREVIEW_BANS,
            details.get("bans_source") or "none",
        )
        return

    details["league_name"] = (
        details.get("league_name")
        or match_summary.get("league_name")
        or TIER1_LEAGUES.get(int(match_summary.get("leagueid") or match_summary.get("league_id") or 0))
        or f"League {int(match_summary.get('leagueid') or match_summary.get('league_id') or 0)}"
    )
    details.setdefault("leagueid", match_summary.get("leagueid") or match_summary.get("league_id"))
    details["radiant_score"] = int(match_summary.get("radiant_score") or details.get("radiant_score") or 0)
    details["dire_score"] = int(match_summary.get("dire_score") or details.get("dire_score") or 0)

    try:
        await send_live_preview_post(details, state, match_id=match_id)
    except Exception as exc:
        logger.error("Failed to post live preview %s: %s", match_id, exc)


async def check_live_matches(live_matches: list[dict] | None = None) -> None:
    if not LIVE_ANNOUNCE_ENABLED:
        return

    if live_matches is None:
        live_matches = get_live_configured_matches()
    announced = get_announced_live_set(state)
    sent = get_sent_set(state)

    for match in live_matches:
        match_id = int(match["match_id"])
        upsert_tracked_live_match(state, match)
        if match_id in announced or match_id in sent:
            continue

        await post_live_preview(match)
    save_state(state)


async def check_and_post() -> None:
    raw_live_rows = get_raw_configured_live_rows() if LIVE_CHECK_ENABLED else None
    live_matches = filter_current_live_matches(raw_live_rows or []) if raw_live_rows is not None else None

    if LIVE_CHECK_ENABLED:
        await check_live_matches(live_matches)

    logger.info("Checking finished tracked matches...")
    sent = get_sent_set(state)
    current_live_ids = {int(match["match_id"]) for match in live_matches or []}
    candidates = [
        match for match in get_finished_tracked_matches(current_live_ids)
        if int(match["match_id"]) not in sent
    ]
    if not candidates:
        candidates = get_recently_deactivated_matches(raw_live_rows)
    if not candidates:
        candidates = get_recent_finished_safety_matches(current_live_ids)
    save_state(state)
    if not candidates:
        logger.info("No finished tracked matches found.")
        return

    candidates.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    new_matches = candidates[:MAX_MATCHES_PER_CHECK]

    if not new_matches:
        logger.info("No new matches found.")
        return

    logger.info("Found %s finished tracked matches.", len(new_matches))
    for match in new_matches:
        await post_match(match)


async def backfill_history(count: int = 10, any_league: bool = False) -> None:
    sent_matches = get_sent_set(state)
    candidates = get_recent_configured_matches()
    if not candidates:
        logger.info("No active configured matches found for backfill.")
        return
    if not any_league:
        candidates = [match for match in candidates if match["leagueid"] in TIER1_LEAGUES]
    candidates = [match for match in candidates if match["match_id"] not in sent_matches]

    candidates.sort(key=lambda item: int(item.get("start_time") or 0), reverse=True)
    candidates = candidates[:count]
    if not candidates:
        logger.info("No matches available for backfill.")
        return

    logger.info("Backfilling %s matches.", len(candidates))
    for match in reversed(candidates):
        await post_match(match)


async def backfill_tier1_history(count: int = 12, per_league: int = 3) -> None:
    sent_matches = get_sent_set(state)
    league_buckets: list[list[dict]] = []

    recent_matches = get_recent_configured_matches()
    for league_id, league_name in TIER1_LEAGUES.items():
        league_candidates = [match for match in recent_matches if match["leagueid"] == int(league_id) and match["match_id"] not in sent_matches]
        if league_candidates:
            league_buckets.append(league_candidates[:per_league])

    candidates: list[dict] = []
    for i in range(per_league):
        for bucket in league_buckets:
            if i < len(bucket):
                candidates.append(bucket[i])
            if len(candidates) >= count:
                break
        if len(candidates) >= count:
            break

    if not candidates:
        logger.info("No tier-1 matches available for backfill.")
        return

    logger.info("Backfilling %s tier-1 matches.", len(candidates))
    for match in reversed(candidates):
        await post_match(match)


async def backfill_current_league(league_id: int, count: int = 3) -> None:
    sent_matches = get_sent_set(state)
    candidates = [
        match
        for match in get_recent_configured_matches()
        if match["leagueid"] == int(league_id)
        if match["match_id"] not in sent_matches
    ][:count]

    if not candidates:
        logger.info("No previous matches found for league_id=%s", league_id)
        return

    logger.info("Posting %s previous matches from current league.", len(candidates))
    for match in reversed(candidates):
        await post_match(match)


async def post_historical_preview_and_result(match_summary: dict) -> None:
    preview_details = _build_historical_preview_details(match_summary)
    if preview_details and has_complete_draft(preview_details) and has_enough_bans(preview_details):
        try:
            await send_historical_preview_post(
                preview_details,
                match_id=int(match_summary["match_id"]),
                post_delay_seconds=POST_DELAY_SECONDS,
            )
        except Exception as exc:
            logger.error("Failed to post historical preview %s: %s", match_summary["match_id"], exc)

    await post_match(match_summary)


async def backfill_league_story(league_id: int, count: int = 0, force: bool = False) -> None:
    sent_matches = set() if force else get_sent_set(state)
    rows = get_league_matches(int(league_id))
    candidates = []
    for row in rows:
        match_id = int(row.get("match_id") or 0)
        if not match_id or match_id in sent_matches:
            continue
        if row.get("radiant_win") is None:
            continue
        candidates.append(
            {
                "match_id": match_id,
                "leagueid": int(row.get("leagueid") or league_id),
                "league_name": TIER1_LEAGUES.get(int(row.get("leagueid") or league_id), row.get("league_name") or f"League {league_id}"),
                "start_time": int(row.get("start_time") or 0),
                "radiant_name": row.get("radiant_name") or "Radiant",
                "dire_name": row.get("dire_name") or "Dire",
                "radiant_team_id": int(row.get("radiant_team_id") or 0),
                "dire_team_id": int(row.get("dire_team_id") or 0),
                "radiant_score": int(row.get("radiant_score") or 0),
                "dire_score": int(row.get("dire_score") or 0),
            }
        )

    candidates.sort(key=lambda item: int(item.get("start_time") or 0))
    if count > 0:
        candidates = candidates[:count]
    if not candidates:
        logger.info("No historical league matches found for league_id=%s", league_id)
        return

    logger.info("Backfilling league story for %s matches (league_id=%s, force=%s).", len(candidates), league_id, force)
    for match in candidates:
        await post_historical_preview_and_result(match)


async def startup() -> None:
    config_errors = validate_runtime_config()
    if config_errors:
        raise RuntimeError("Invalid runtime config:\n- " + "\n- ".join(config_errors))

    assert bot is not None
    logger.info("Bot starting...")
    logger.info("Initialization complete.")


async def main(
    run_once: bool = False,
    backfill_count: int = 0,
    backfill_tier1_count: int = 0,
    current_league_backfill: int = 0,
    league_story_backfill: int = 0,
    league_story_count: int = 0,
    force_story_backfill: bool = False,
    any_league: bool = False,
) -> None:
    await startup()

    if league_story_backfill:
        await backfill_league_story(league_story_backfill, count=league_story_count, force=force_story_backfill)
        return
    if current_league_backfill:
        await backfill_current_league(current_league_backfill, count=3)
        return
    if backfill_tier1_count:
        await backfill_tier1_history(backfill_tier1_count)
        return
    if backfill_count:
        await backfill_history(backfill_count, any_league=any_league)
        return
    if run_once:
        await check_and_post()
        return

    await run_interval_scheduler(check_and_post, interval_minutes=CHECK_INTERVAL_MINUTES)


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="Dota 2 Telegram match bot")
    parser.add_argument("--validate-config", action="store_true", help="validate required runtime config and exit")
    parser.add_argument("--once", action="store_true", help="run one check and exit")
    parser.add_argument("--backfill", type=int, default=0, help="post N older matches and exit")
    parser.add_argument("--backfill-tier1", type=int, default=0, help="post N tier-1 main-event matches and exit")
    parser.add_argument("--backfill-league", type=int, default=0, help="post 3 previous matches from the given league id")
    parser.add_argument("--backfill-league-story", type=int, default=0, help="post preview+result history for all completed matches in the given league id")
    parser.add_argument("--story-count", type=int, default=0, help="limit --backfill-league-story to the first N matches in chronological order")
    parser.add_argument("--force-story-backfill", action="store_true", help="ignore sent state for --backfill-league-story")
    parser.add_argument("--any-league", action="store_true", help="use latest pro matches from any league for --backfill")
    args = parser.parse_args()

    if args.validate_config:
        errors = validate_runtime_config()
        if errors:
            for error in errors:
                print(error)
            raise SystemExit(1)
        print("Runtime config is valid.")
        raise SystemExit(0)

    asyncio.run(
        main(
            run_once=args.once,
            backfill_count=args.backfill,
            backfill_tier1_count=args.backfill_tier1,
            current_league_backfill=args.backfill_league,
            league_story_backfill=args.backfill_league_story,
            league_story_count=args.story_count,
            force_story_backfill=args.force_story_backfill,
            any_league=args.any_league,
        )
    )


if __name__ == "__main__":
    cli_main()
