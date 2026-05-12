from __future__ import annotations

from src.config.constants import TIER1_LEAGUES, is_allowed_tier1_league
from src.models.match import MatchModel
from src.models.player import PlayerModel
from src.services.opendota_service import OpenDotaService
from src.services.steam_service import SteamService
from src.services.stratz_service import StratzService
from src.services.neutral_cache import NeutralItemCache

NEUTRAL_ENHANCEMENT_IDS = set(range(1583, 1597)) | set(range(1856, 1874))


class MatchPipelineService:
    def __init__(
        self,
        steam: SteamService,
        opendota: OpenDotaService,
        stratz: StratzService,
        neutral_cache: NeutralItemCache | None = None,
        resolve_metadata: bool = False,
    ) -> None:
        self.steam = steam
        self.opendota = opendota
        self.stratz = stratz
        self.neutral_cache = neutral_cache
        self.resolve_metadata = resolve_metadata

    @staticmethod
    def _player_is_radiant(player: dict) -> bool:
        if "isRadiant" in player:
            return bool(player.get("isRadiant"))
        if "is_radiant" in player:
            return bool(player.get("is_radiant"))
        if "team" in player:
            return int(player.get("team") or 0) == 0
        if "player_slot" in player:
            return int(player.get("player_slot") or 0) < 128
        return False

    @staticmethod
    def _hero_meta(hero_id: int, resolve_metadata: bool) -> dict:
        if not resolve_metadata or not hero_id:
            return {}
        try:
            from stratz_fetcher import get_hero_map

            return get_hero_map().get(int(hero_id), {})
        except Exception:
            return {}

    @staticmethod
    def _item_map(resolve_metadata: bool) -> dict[int, dict]:
        if not resolve_metadata:
            return {}
        try:
            from stratz_fetcher import get_item_map

            return get_item_map()
        except Exception:
            return {}

    @staticmethod
    def _item_entry(item_id, item_map: dict[int, dict]) -> dict | None:
        try:
            resolved_id = int(item_id or 0)
        except (TypeError, ValueError):
            return None
        item = item_map.get(resolved_id)
        if not item:
            return None
        return {
            "id": int(item.get("id") or resolved_id),
            "short_name": item.get("short_name") or "",
            "display_name": item.get("display_name") or "",
        }

    @staticmethod
    def _extract_items(player: dict, prefix: str, count: int, item_map: dict[int, dict]) -> list[dict]:
        explicit = player.get("items" if prefix == "item" else "backpack")
        if isinstance(explicit, list) and explicit:
            return [dict(item) if isinstance(item, dict) else {"id": int(item)} for item in explicit if item]
        items = []
        for slot in range(count):
            entry = MatchPipelineService._item_entry(
                player.get(f"{prefix}_{slot}") or player.get(f"{prefix}{slot}") or player.get(f"{prefix}{slot}Id"),
                item_map,
            )
            if entry:
                items.append(entry)
        return items

    @staticmethod
    def _extract_buffs(player: dict, item_map: dict[int, dict]) -> list[dict]:
        explicit = player.get("buffs")
        if isinstance(explicit, list) and explicit:
            return [dict(item) if isinstance(item, dict) else {"id": int(item)} for item in explicit if item]
        buffs = []
        for flag, item_id in (("aghanims_scepter", 108), ("aghanims_shard", 609), ("moonshard", 247)):
            if int(player.get(flag) or player.get(flag.replace("_", "")) or 0):
                item = MatchPipelineService._item_entry(item_id, item_map)
                if item:
                    buffs.append(item)
        return buffs

    @staticmethod
    def _extract_unit_loadouts(player: dict, item_map: dict[int, dict]) -> list[dict]:
        units = player.get("additional_units") or []
        result = []
        for unit in units:
            result.append(
                {
                    "unit_name": unit.get("unitname") or unit.get("unit_name") or "",
                    "items": MatchPipelineService._extract_items(unit, "item", 6, item_map),
                    "backpack": MatchPipelineService._extract_items(unit, "backpack", 3, item_map),
                    "neutral_item": MatchPipelineService._extract_neutral_item(unit, item_map),
                    "buffs": [],
                }
            )
        return result

    @staticmethod
    def _extract_bans(payload: dict, resolve_metadata: bool = False) -> list[dict]:
        explicit_bans = payload.get("bans")
        if isinstance(explicit_bans, list) and explicit_bans:
            return explicit_bans
        bans: list[dict] = []
        for row in payload.get("picks_bans") or payload.get("pickBans") or []:
            is_pick = row.get("is_pick")
            if is_pick is None:
                is_pick = row.get("isPick")
            if bool(is_pick):
                continue
            hero_id = row.get("hero_id") or row.get("heroId") or row.get("bannedHeroId")
            if hero_id:
                resolved_hero_id = int(hero_id)
                hero = MatchPipelineService._hero_meta(resolved_hero_id, resolve_metadata)
                if row.get("team") is not None:
                    is_radiant = int(row.get("team") or 0) == 0
                else:
                    is_radiant = bool(row.get("isRadiant") if "isRadiant" in row else row.get("is_radiant"))
                bans.append(
                    {
                        "hero_id": resolved_hero_id,
                        "order": int(row.get("order") or len(bans)),
                        **(
                            {
                                "hero_name": hero.get("display_name") or row.get("hero_name") or "",
                                "hero_short_name": hero.get("short_name") or row.get("hero_short_name") or "",
                                "is_radiant": is_radiant,
                            }
                            if resolve_metadata
                            else {}
                        ),
                    }
                )
        return bans

    @staticmethod
    def _extract_neutral_item(player: dict, item_map: dict[int, dict] | None = None) -> dict | None:
        direct = player.get("neutral_item")
        if isinstance(direct, dict) and direct.get("short_name") and not str(direct.get("short_name")).startswith("enhancement_"):
            return direct

        for entry in reversed(player.get("neutral_item_history") or []):
            short_name = entry.get("item_neutral")
            if short_name:
                return {
                    "id": 0,
                    "short_name": str(short_name),
                    "display_name": str(short_name).replace("_", " ").title(),
                }

        for key in ("item_neutral", "item_neutral_id", "neutral0Id", "neutral0_id", "neutralItem", "item_neutral2"):
            value = player.get(key)
            if not value:
                continue
            try:
                resolved_id = int(value)
            except (TypeError, ValueError):
                resolved_id = 0
            if resolved_id in NEUTRAL_ENHANCEMENT_IDS:
                continue
            if item_map:
                item = MatchPipelineService._item_entry(value, item_map)
                if item and not str(item.get("short_name") or "").startswith("enhancement_"):
                    return item
            return {
                "id": resolved_id,
                "short_name": player.get("neutral_short_name") or player.get("neutral_item_short_name") or "",
                "display_name": player.get("neutral_display_name") or player.get("neutral_item_name") or "",
            }
        return None

    @staticmethod
    def _team_logo_url(team_id: int, logo_id: str = "") -> str:
        if team_id:
            try:
                from opendota_discovery import get_team_info

                logo_url = get_team_info(int(team_id)).get("logo_url") or ""
                if logo_url:
                    return logo_url
            except Exception:
                pass
        if logo_id and "/" in str(logo_id):
            return str(logo_id)
        return ""

    @staticmethod
    def _to_match_model(payload: dict) -> MatchModel:
        resolve_metadata = bool(payload.get("_resolve_metadata"))
        item_map = MatchPipelineService._item_map(resolve_metadata)
        players = [
            (lambda hero_id, hero: PlayerModel(
                account_id=int(player.get("account_id") or 0),
                name=player.get("name") or player.get("personaname") or player.get("pro_name") or "Player",
                hero_id=hero_id,
                hero_name=player.get("hero_name") or hero.get("display_name") or "",
                hero_short_name=player.get("hero_short_name") or hero.get("short_name") or "",
                is_radiant=MatchPipelineService._player_is_radiant(player),
                kills=int(player.get("kills") or 0),
                deaths=int(player.get("deaths") or 0),
                assists=int(player.get("assists") or 0),
                gold_per_min=int(player.get("gold_per_min") or player.get("goldPerMinute") or 0),
                xp_per_min=int(player.get("xp_per_min") or player.get("experiencePerMinute") or 0),
                net_worth=int(player.get("net_worth") or player.get("networth") or 0),
                hero_damage=int(player.get("hero_damage") or player.get("heroDamage") or 0),
                hero_healing=int(player.get("hero_healing") or player.get("heroHealing") or 0),
                tower_damage=int(player.get("tower_damage") or player.get("towerDamage") or 0),
                items=MatchPipelineService._extract_items(player, "item", 6, item_map),
                backpack=MatchPipelineService._extract_items(player, "backpack", 3, item_map),
                buffs=MatchPipelineService._extract_buffs(player, item_map),
                neutral_item=MatchPipelineService._extract_neutral_item(player, item_map),
                additional_units=MatchPipelineService._extract_unit_loadouts(player, item_map),
            ))(
                int(player.get("hero_id") or player.get("heroId") or 0),
                MatchPipelineService._hero_meta(int(player.get("hero_id") or player.get("heroId") or 0), resolve_metadata),
            )
            for player in payload.get("players") or []
        ]
        return MatchModel(
            match_id=int(payload.get("match_id") or payload.get("matchId") or payload.get("id") or 0),
            league_id=int(payload.get("leagueid") or payload.get("league_id") or payload.get("leagueId") or 0),
            league_name=payload.get("league_name") or "",
            radiant_name=payload.get("radiant_name") or payload.get("team_name_radiant") or "Radiant",
            dire_name=payload.get("dire_name") or payload.get("team_name_dire") or "Dire",
            radiant_logo_url=payload.get("radiant_logo_url") or "",
            dire_logo_url=payload.get("dire_logo_url") or "",
            radiant_score=int(payload.get("radiant_score") or 0),
            dire_score=int(payload.get("dire_score") or 0),
            duration=int(payload.get("duration") or 0),
            radiant_win=payload.get("radiant_win"),
            players=players,
            bans=MatchPipelineService._extract_bans(payload, resolve_metadata),
        )

    @staticmethod
    def _live_payload_from_steam(game: dict) -> dict:
        league_id = int(game.get("league_id") or game.get("leagueid") or 0)
        league_name = game.get("league_name") or TIER1_LEAGUES.get(league_id, "")
        return {
            "match_id": int(game.get("match_id") or 0),
            "leagueid": league_id,
            "league_name": league_name,
            "radiant_name": (game.get("radiant_team") or {}).get("team_name") or "Radiant",
            "dire_name": (game.get("dire_team") or {}).get("team_name") or "Dire",
            "radiant_score": int(game.get("radiant_score") or 0),
            "dire_score": int(game.get("dire_score") or 0),
            "duration": int(game.get("game_time") or 0),
            "players": game.get("players") or [],
        }

    async def get_live_tier1_matches(self) -> list[MatchModel]:
        steam_games = await self.steam.get_live_games()
        opendota_live = await self.opendota.get_live_matches()

        steam_by_id = {
            int(game.get("match_id") or 0): game
            for game in steam_games
            if int(game.get("match_id") or 0)
        }

        normalized_by_id: dict[int, MatchModel] = {}
        for row in opendota_live:
            league_id = int(row.get("league_id") or row.get("leagueid") or 0)
            league_name = row.get("league_name") or TIER1_LEAGUES.get(league_id, "")
            if not is_allowed_tier1_league(league_id, league_name):
                continue
            match_id = int(row.get("match_id") or 0)
            if not match_id:
                continue
            steam_row = steam_by_id.get(match_id, {})
            payload = {
                "match_id": match_id,
                "leagueid": league_id,
                "league_name": league_name,
                "radiant_name": row.get("team_name_radiant") or "Radiant",
                "dire_name": row.get("team_name_dire") or "Dire",
                "radiant_score": int(row.get("radiant_score") or steam_row.get("radiant_score") or 0),
                "dire_score": int(row.get("dire_score") or steam_row.get("dire_score") or 0),
                "duration": int(row.get("game_time") or steam_row.get("game_time") or 0),
                "players": row.get("players") or [],
                "radiant_logo_url": self._team_logo_url(int(row.get("team_id_radiant") or 0), str(row.get("team_logo_radiant") or "")),
                "dire_logo_url": self._team_logo_url(int(row.get("team_id_dire") or 0), str(row.get("team_logo_dire") or "")),
            }
            snapshot = await self.opendota.get_match_snapshot(match_id)
            if snapshot:
                snapshot_players = snapshot.get("players") or []
                has_live_neutral = any(player.get("neutral_item") or player.get("item_neutral") for player in payload["players"])
                if snapshot_players and not has_live_neutral and (not payload["players"] or len(payload["players"]) != 10):
                    payload["players"] = snapshot_players
                payload["picks_bans"] = snapshot.get("picks_bans") or []
                payload["_resolve_metadata"] = self.resolve_metadata
            normalized_by_id[match_id] = self._to_match_model(payload)

        for game in steam_games:
            match_id = int(game.get("match_id") or 0)
            league_id = int(game.get("league_id") or game.get("leagueid") or 0)
            league_name = game.get("league_name") or TIER1_LEAGUES.get(league_id, "")
            if not match_id or not is_allowed_tier1_league(league_id, league_name) or match_id in normalized_by_id:
                continue
            payload = self._live_payload_from_steam(game)
            snapshot = await self.opendota.get_match_snapshot(match_id)
            if snapshot:
                snapshot_players = snapshot.get("players") or []
                if snapshot_players and (not payload["players"] or len(payload["players"]) != 10):
                    payload["players"] = snapshot_players
                payload["picks_bans"] = snapshot.get("picks_bans") or []
                payload["_resolve_metadata"] = self.resolve_metadata
            normalized_by_id[match_id] = self._to_match_model(payload)

        normalized = list(normalized_by_id.values())
        normalized.sort(key=lambda item: item.duration, reverse=True)
        if self.neutral_cache:
            for match in normalized:
                self.neutral_cache.remember_match(match)
        return normalized

    async def get_result_match(self, match_id: int, league_id: int = 0) -> MatchModel | None:
        snapshot = await self.opendota.get_match_snapshot(match_id)
        if snapshot and snapshot.get("players"):
            payload = {
                "match_id": match_id,
                "leagueid": int(snapshot.get("leagueid") or league_id or 0),
                "league_name": TIER1_LEAGUES.get(int(snapshot.get("leagueid") or league_id or 0), ""),
                "radiant_name": snapshot.get("radiant_name") or "Radiant",
                "dire_name": snapshot.get("dire_name") or "Dire",
                "radiant_score": int(snapshot.get("radiant_score") or 0),
                "dire_score": int(snapshot.get("dire_score") or 0),
                "duration": int(snapshot.get("duration") or 0),
                "radiant_win": snapshot.get("radiant_win"),
                "players": snapshot.get("players") or [],
                "picks_bans": snapshot.get("picks_bans") or [],
                "radiant_logo_url": self._team_logo_url(int(snapshot.get("radiant_team_id") or 0)),
                "dire_logo_url": self._team_logo_url(int(snapshot.get("dire_team_id") or 0)),
                "_resolve_metadata": self.resolve_metadata,
            }
            result = self._to_match_model(payload)
            if self.neutral_cache:
                self.neutral_cache.apply_to_match(result)
            return result

        stratz_match = await self.stratz.get_match_details(match_id)
        if not stratz_match:
            return None

        payload = {
            "match_id": int(stratz_match.get("id") or match_id),
            "leagueid": int(league_id or 0),
            "league_name": TIER1_LEAGUES.get(int(league_id or 0), ""),
            "duration": int(stratz_match.get("durationSeconds") or 0),
            "radiant_win": stratz_match.get("didRadiantWin"),
        }
        return self._to_match_model(payload)
