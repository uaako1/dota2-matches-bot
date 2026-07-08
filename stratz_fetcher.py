import logging
from functools import lru_cache
import time

from config import STRATZ_TOKEN, TIER1_LEAGUES, is_allowed_tier1_league
from src.core import shared_http

logger = logging.getLogger(__name__)

STRATZ_GRAPHQL = "https://api.stratz.com/graphql"
DOTACONSTANTS_HEROES = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/heroes.json"
DOTACONSTANTS_ITEMS = "https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json"
STRATZ_MIN_INTERVAL_SECONDS = 0.25
STRATZ_BLOCK_COOLDOWN_SECONDS = 300

_last_call_at = 0.0
_cooldown_until = 0.0


def has_stratz_token():
    return bool(STRATZ_TOKEN)


def _wait_for_stratz_slot() -> bool:
    global _last_call_at
    now = time.monotonic()
    if now < _cooldown_until:
        return False
    wait_seconds = STRATZ_MIN_INTERVAL_SECONDS - (now - _last_call_at)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _last_call_at = time.monotonic()
    return True


def stratz_graphql(query, variables=None):
    global _cooldown_until
    if not STRATZ_TOKEN:
        return None
    if not _wait_for_stratz_slot():
        return None

    response = shared_http.post_json(
        STRATZ_GRAPHQL,
        json_body={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {STRATZ_TOKEN}",
            "User-Agent": "DotaWatchBot/2.1 contact:telegram:@dotawatch",
            "Accept": "application/json",
        },
        timeout=30,
    )
    if response is None:
        logger.warning("STRATZ request failed.")
        return None

    if response.status_code == 429:
        retry_after = int(response.headers.get("retry-after") or 60)
        _cooldown_until = time.monotonic() + retry_after
        logger.warning("STRATZ rate limited. Cooling down for %ss.", retry_after)
        return None

    if response.status_code == 403 and "different IP" in response.text:
        logger.warning("STRATZ token is locked to another IP. Create a new token on this server/PC.")
        _cooldown_until = time.monotonic() + STRATZ_BLOCK_COOLDOWN_SECONDS
        return None

    if response.status_code == 403:
        content_type = (response.headers.get("content-type") or "").lower()
        if "text/html" in content_type and "Just a moment" in response.text:
            logger.warning(
                "STRATZ request was blocked by Cloudflare challenge before GraphQL. "
                "Token may be valid, but this environment/IP cannot call api.stratz.com directly."
            )
            _cooldown_until = time.monotonic() + STRATZ_BLOCK_COOLDOWN_SECONDS
            return None
        logger.warning("STRATZ returned HTTP 403. Cooling down for %ss.", STRATZ_BLOCK_COOLDOWN_SECONDS)
        _cooldown_until = time.monotonic() + STRATZ_BLOCK_COOLDOWN_SECONDS
        return None

    if response.status_code != 200:
        logger.warning("STRATZ returned HTTP %s: %s", response.status_code, response.text[:300])
        return None

    try:
        data = response.json()
    except ValueError:
        logger.warning("STRATZ returned non-JSON response: %s", response.text[:300])
        return None

    if data.get("errors"):
        logger.warning("STRATZ GraphQL errors: %s", data["errors"][:2])
        return None

    return data.get("data")


def _fetch_constants_json(url: str):
    try:
        response = shared_http.get(url, timeout=30)
        if response is None:
            return {}
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("Constants fallback request failed for %s: %s", url, exc)
        return {}


@lru_cache(maxsize=1)
def get_hero_map():
    query = """
    {
      constants {
        heroes {
          id
          shortName
          displayName
        }
      }
    }
    """
    heroes = (((stratz_graphql(query) or {}).get("constants") or {}).get("heroes")) or []
    if heroes:
        return {
            int(hero["id"]): {
                "id": int(hero["id"]),
                "short_name": hero.get("shortName") or "",
                "display_name": hero.get("displayName") or "",
            }
            for hero in heroes
            if hero.get("id") is not None
        }

    fallback = _fetch_constants_json(DOTACONSTANTS_HEROES)
    hero_map = {}
    for key, hero in (fallback or {}).items():
        hero_id = int(hero.get("id") or key or 0)
        if not hero_id:
            continue
        name = hero.get("localized_name") or hero.get("name") or ""
        short_name = (hero.get("name") or "").replace("npc_dota_hero_", "")
        hero_map[hero_id] = {
            "id": hero_id,
            "short_name": short_name,
            "display_name": name,
        }
    return hero_map


@lru_cache(maxsize=1)
def get_item_map():
    query = """
    {
      constants {
        items {
          id
          shortName
          displayName
        }
      }
    }
    """
    items = (((stratz_graphql(query) or {}).get("constants") or {}).get("items")) or []
    item_map = {}
    if items:
        item_map.update({
            int(item["id"]): {
                "id": int(item["id"]),
                "short_name": item.get("shortName") or "",
                "display_name": item.get("displayName") or "",
            }
            for item in items
            if item.get("id") is not None
        })

    fallback = _fetch_constants_json(DOTACONSTANTS_ITEMS)
    for key, item in (fallback or {}).items():
        item_id = int(item.get("id") or key or 0)
        if not item_id:
            continue
        if item_id in item_map:
            continue
        short_name = (item.get("name") or str(key) or "").removeprefix("item_")
        item_map[item_id] = {
            "id": item_id,
            "short_name": short_name,
            "display_name": item.get("dname") or item.get("localized_name") or item.get("name") or "",
        }
    return item_map


def _league_is_tier1(league):
    if not league:
        return False
    league_id = league.get("id") or league.get("leagueId")
    name = league.get("displayName") or league.get("name") or ""
    return is_allowed_tier1_league(league_id, name)


def _preferred_player_name(steam_account):
    steam_account = steam_account or {}
    pro = steam_account.get("proSteamAccount") or {}
    return (
        (pro.get("name") or "").strip()
        or (steam_account.get("name") or "").strip()
        or "Anonymous"
    )


def _item_entry(item_id, item_map):
    item = item_map.get(int(item_id or 0))
    if not item:
        return None
    return {
        "id": item["id"],
        "short_name": item["short_name"],
        "display_name": item["display_name"],
    }


def _player_buff_items(player, item_map):
    buffs = []
    if int(player.get("aghanimsScepter") or player.get("aghanims_scepter") or 0):
        item = _item_entry(108, item_map)
        if item:
            buffs.append(item)
    if int(player.get("aghanimsShard") or player.get("aghanims_shard") or 0):
        item = _item_entry(609, item_map)
        if item:
            buffs.append(item)
    if int(player.get("moonshard") or player.get("moonShard") or 0):
        item = _item_entry(247, item_map)
        if item:
            buffs.append(item)
    return buffs


def get_live_matches():
    query = """
    query($leagueIds: [Int]) {
      live {
        matches(request: { leagueIds: $leagueIds, isCompleted: false, isLeague: true, take: 50 }) {
          matchId
          gameTime
          gameMinute
          gameState
          radiantScore
          direScore
          league { id name displayName }
          radiantTeam { id name tag logo }
          direTeam { id name tag logo }
        }
      }
    }
    """
    data = stratz_graphql(query, {"leagueIds": list(TIER1_LEAGUES)})
    matches = (((data or {}).get("live") or {}).get("matches")) or []
    normalized = []

    for match in matches:
        league = match.get("league") or {}
        if not _league_is_tier1(league):
            continue

        match_id = match.get("matchId") or match.get("id")
        if not match_id:
            continue

        radiant = match.get("radiantTeam") or {}
        dire = match.get("direTeam") or {}
        normalized.append(
            {
                "match_id": int(match_id),
                "leagueid": league.get("id"),
                "league_name": league.get("displayName") or league.get("name") or "Tier-1 Live",
                "radiant_name": radiant.get("name") or radiant.get("tag") or "Radiant",
                "dire_name": dire.get("name") or dire.get("tag") or "Dire",
                "radiant_score": match.get("radiantScore") or 0,
                "dire_score": match.get("direScore") or 0,
                "game_time": match.get("gameTime") or (match.get("gameMinute") or 0) * 60,
                "game_state": match.get("gameState"),
            }
        )

    return normalized


def normalize_match(match, league_name_override=None):
    if not match:
        return None

    hero_map = get_hero_map()
    item_map = get_item_map()
    radiant_team = match.get("radiantTeam") or {}
    dire_team = match.get("direTeam") or {}
    league = match.get("league") or {}

    players = []
    radiant_score = 0
    dire_score = 0
    raw_players = match.get("players") or []

    for idx, player in enumerate(raw_players):
        hero = player.get("hero") or {}
        steam_account = player.get("steamAccount") or {}
        kills = int(player.get("kills") or 0)
        if player.get("isRadiant"):
            radiant_score += kills
        else:
            dire_score += kills

        items = []
        backpack = []
        for slot in range(6):
            entry = _item_entry(player.get(f"item{slot}Id"), item_map)
            if entry:
                items.append(entry)
        for slot in range(3):
            entry = _item_entry(player.get(f"backpack{slot}Id"), item_map)
            if entry:
                backpack.append(entry)
        neutral = _item_entry(player.get("neutral0Id"), item_map)

        players.append(
            {
                "index": idx,
                "isRadiant": bool(player.get("isRadiant")),
                "hero_id": hero.get("id"),
                "hero_name": hero.get("displayName") or "",
                "hero_short_name": hero.get("shortName") or "",
                "kills": kills,
                "deaths": int(player.get("deaths") or 0),
                "assists": int(player.get("assists") or 0),
                "last_hits": int(player.get("numLastHits") or 0),
                "denies": int(player.get("numDenies") or 0),
                "gold_per_min": int(player.get("goldPerMinute") or 0),
                "xp_per_min": int(player.get("experiencePerMinute") or 0),
                "net_worth": int(player.get("networth") or 0),
                "hero_damage": int(player.get("heroDamage") or 0),
                "hero_healing": int(player.get("heroHealing") or 0),
                "tower_damage": int(player.get("towerDamage") or 0),
                "name": _preferred_player_name(steam_account),
                "steam_name": (steam_account.get("name") or "").strip(),
                "real_name": (steam_account.get("realName") or "").strip(),
                "pro_name": ((steam_account.get("proSteamAccount") or {}).get("name") or "").strip(),
                "items": items,
                "backpack": backpack,
                "neutral_item": neutral,
                "buffs": _player_buff_items(player, item_map),
            }
        )

    picks = []
    bans = []
    player_by_index = {player["index"]: player for player in players}
    for entry in sorted(match.get("pickBans") or [], key=lambda x: int(x.get("order") or 0)):
        is_pick = bool(entry.get("isPick"))
        is_radiant = bool(entry.get("isRadiant"))
        hero_id = entry.get("heroId") or entry.get("bannedHeroId")
        hero_meta = hero_map.get(int(hero_id or 0), {})
        item = {
            "order": int(entry.get("order") or 0),
            "is_radiant": is_radiant,
            "hero_id": int(hero_id or 0),
            "hero_name": hero_meta.get("display_name") or "",
            "hero_short_name": hero_meta.get("short_name") or "",
        }
        if is_pick:
            player = player_by_index.get(int(entry.get("playerIndex") or -1), {})
            item["player_name"] = player.get("name") or ""
            picks.append(item)
        else:
            bans.append(item)

    return {
        "match_id": match.get("id"),
        "duration": int(match.get("durationSeconds") or 0),
        "radiant_win": bool(match.get("didRadiantWin")),
        "radiant_score": int(radiant_score),
        "dire_score": int(dire_score),
        "radiant_name": radiant_team.get("name") or "Radiant",
        "dire_name": dire_team.get("name") or "Dire",
        "leagueid": match.get("leagueId"),
        "league_name": league_name_override or league.get("displayName") or league.get("name"),
        "radiant_team": {"id": radiant_team.get("id"), "logo_url": radiant_team.get("logo")},
        "dire_team": {"id": dire_team.get("id"), "logo_url": dire_team.get("logo")},
        "players": players,
        "picks": picks,
        "bans": bans,
    }


@lru_cache(maxsize=512)
def get_match_details(match_id, league_name_override=None):
    query = """
    query($id: Long!) {
      match(id: $id) {
        id
        didRadiantWin
        durationSeconds
        leagueId
        league { id displayName name }
        radiantTeam { id name logo }
        direTeam { id name logo }
        players {
          isRadiant
          kills
          deaths
          assists
          numLastHits
          numDenies
          goldPerMinute
          experiencePerMinute
          networth
          heroDamage
          heroHealing
          towerDamage
          item0Id
          item1Id
          item2Id
          item3Id
          item4Id
          item5Id
          backpack0Id
          backpack1Id
          backpack2Id
          neutral0Id
          hero { id displayName shortName }
          steamAccount {
            name
            realName
            proSteamAccount { name realName }
          }
        }
        pickBans {
          isPick
          heroId
          bannedHeroId
          order
          isRadiant
          playerIndex
        }
      }
    }
    """
    data = stratz_graphql(query, {"id": int(match_id)})
    match = (data or {}).get("match")
    return normalize_match(match, league_name_override=league_name_override)


def get_recent_tier1_leagues(take=80):
    query = """
    {
      leagues(request:{tiers:[PROFESSIONAL], take:80, skip:0, orderBy:LAST_MATCH_TIME_THEN_TIER}) {
        id
        displayName
        lastMatchDate
        hasLiveMatches
      }
    }
    """
    data = stratz_graphql(query) or {}
    leagues = data.get("leagues") or []
    result = []
    for league in leagues:
        if _league_is_tier1({"id": league.get("id"), "displayName": league.get("displayName")}):
            result.append(
                {
                    "leagueid": int(league["id"]),
                    "league_name": league.get("displayName") or TIER1_LEAGUES.get(league.get("id")),
                    "last_match_date": int(league.get("lastMatchDate") or 0),
                    "has_live_matches": bool(league.get("hasLiveMatches")),
                }
            )
    return result[:take]


def get_league_recent_matches(league_id, league_name=None, take=12):
    query = """
    query($leagueId:Int!, $take:Int!) {
      leagues(request:{leagueId:$leagueId, take:1, skip:0}) {
        id
        displayName
        matches(request:{take:$take, skip:0, isStats:true}) {
          id
          startDateTime
          durationSeconds
        }
      }
    }
    """
    data = stratz_graphql(query, {"leagueId": int(league_id), "take": int(take)}) or {}
    leagues = data.get("leagues") or []
    if not leagues:
        return []

    league = leagues[0]
    resolved_name = league_name or league.get("displayName") or TIER1_LEAGUES.get(int(league_id))
    matches = []
    for match in league.get("matches") or []:
        matches.append(
            {
                "match_id": int(match["id"]),
                "leagueid": int(league_id),
                "league_name": resolved_name,
                "start_time": int(match.get("startDateTime") or 0),
                "duration": int(match.get("durationSeconds") or 0),
            }
        )
    return matches
