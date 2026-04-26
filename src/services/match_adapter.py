from __future__ import annotations

from src.models.match import MatchModel
from src.models.player import PlayerModel


def _item_payload(item) -> dict:
    if isinstance(item, dict):
        return dict(item)
    if item:
        return {"id": int(item)}
    return {}


def _player_to_legacy(player: PlayerModel) -> dict:
    return {
        "account_id": player.account_id,
        "name": player.name,
        "personaname": player.name,
        "hero_id": player.hero_id,
        "hero_name": player.hero_name,
        "hero_short_name": player.hero_short_name,
        "isRadiant": player.is_radiant,
        "kills": player.kills,
        "deaths": player.deaths,
        "assists": player.assists,
        "gold_per_min": player.gold_per_min,
        "xp_per_min": player.xp_per_min,
        "net_worth": player.net_worth,
        "hero_damage": player.hero_damage,
        "hero_healing": player.hero_healing,
        "tower_damage": player.tower_damage,
        "items": [_item_payload(item) for item in player.items],
        "backpack": [_item_payload(item) for item in player.backpack],
        "buffs": [_item_payload(buff) for buff in player.buffs],
        "neutral_item": _item_payload(player.neutral_item) if player.neutral_item else None,
        "additional_units": list(player.additional_units),
    }


def match_to_legacy_dict(match: MatchModel) -> dict:
    return {
        "match_id": match.match_id,
        "matchId": match.match_id,
        "leagueid": match.league_id,
        "league_id": match.league_id,
        "league_name": match.league_name,
        "radiant_name": match.radiant_name,
        "dire_name": match.dire_name,
        "radiant_team": {"logo_url": match.radiant_logo_url},
        "dire_team": {"logo_url": match.dire_logo_url},
        "radiant_score": match.radiant_score,
        "dire_score": match.dire_score,
        "duration": match.duration,
        "radiant_win": match.radiant_win,
        "players": [_player_to_legacy(player) for player in match.players],
        "bans": list(match.bans),
    }


def missing_neutral_players(match: MatchModel) -> list[str]:
    missing: list[str] = []
    for player in match.players:
        if player.neutral_item:
            continue
        if not player.hero_id:
            continue
        missing.append(player.name or f"hero:{player.hero_id}")
    return missing
