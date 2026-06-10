import os
from pathlib import Path

# ===== Bot settings =====
DEFAULT_CHANNEL_ID = "@dotawatch"
DEFAULT_STREAM_URL = os.getenv("DEFAULT_STREAM_URL", "https://www.twitch.tv/dota2_paragon_ru").strip()

CHECK_INTERVAL_MINUTES = 4
MAX_MATCHES_PER_CHECK = 6
LIVE_MATCHES_FETCH_LIMIT = 60
RECENT_MATCHES_FETCH_LIMIT = 60
SAFETY_MATCHES_FETCH_LIMIT = 24
POST_DELAY_SECONDS = 1
LIVE_CHECK_ENABLED = True
LIVE_ANNOUNCE_ENABLED = True
ACTIVE_LEAGUE_LOOKBACK_DAYS = 45
MIN_PREVIEW_BANS = int(os.getenv("MIN_PREVIEW_BANS", "14"))

STATE_FILE = os.getenv("STATE_FILE", "data/bot_state.json").strip()

# Strict tier-1/main-event league IDs. No Division 2, no qualifiers, no minor leagues.
TIER1_LEAGUES = {
    18324: "The International 2025",
    16935: "The International 2024",
    19422: "ESL One Birmingham 2026",
    17795: "ESL One Raleigh 2025",
    19101: "BLAST Slam VII",
    19099: "BLAST Slam VI",
    17414: "BLAST Slam I",
    19543: "PGL Wallachia 2026 Season 8",
    19435: "PGL Wallachia 2026 Season 7",
    18920: "PGL Wallachia 2025 Season 6",
    18358: "PGL Wallachia 2025 Season 5",
    18058: "PGL Wallachia 2025 Season 4",
    19269: "DreamLeague Season 28",
    19696: "DreamLeague Season 29",
    18988: "DreamLeague Season 27",
    18111: "DreamLeague Season 26",
    17765: "DreamLeague Season 25",
    18863: "FISSURE PLAYGROUND 2",
    16881: "Riyadh Masters 2024 at Esports World Cup",
}

ALLOWED_LEAGUE_IDS = set(TIER1_LEAGUES)
LEAGUE_NAMES = dict(TIER1_LEAGUES)

TEAM_LOGO_OVERRIDES = {
    36: "https://steamcdn-a.akamaihd.net/apps/dota2/images/team_logos/36.png",
    2163: "https://steamcdn-a.akamaihd.net/apps/dota2/images/team_logos/2163.png",
    2586976: "https://steamcdn-a.akamaihd.net/apps/dota2/images/team_logos/2586976.png",
    726228: "https://steamcdn-a.akamaihd.net/apps/dota2/images/team_logos/726228.png",
    7119388: "https://cdn.steamusercontent.com/ugc/1839179120711951766/CD7E0885CB527334205CC7885E9C101B7BC17702/",
    8255888: "https://cdn.steamusercontent.com/ugc/9995426432403529725/51E13136D4CCC8C7D8062861541A1D13B8ED87E0/",
    8261500: "https://cdn.steamusercontent.com/ugc/2402194226059610590/E3CF4B6C4B2CFB974A9B415141E4A37317AD4D80/",
    8291895: "https://cdn.steamusercontent.com/ugc/2031716132171967904/07B168B8063D9B22CDAD53AB421ECAF3D4B2E07E/",
    8599101: "https://cdn.steamusercontent.com/ugc/1850419664501191993/5DAAB68FB5604D29E1792A0F35E74B3FE3F3A026/",
    9247354: "https://cdn.steamusercontent.com/ugc/2314350571781870059/2B5C9FE9BA0A2DC303A13261444532AA08352843/",
    9303484: "https://cdn.steamusercontent.com/ugc/2471984170520125054/B066431AF4D322D300DD5180CEC8F6BA0E85A7F5/",
    9338413: "https://cdn.steamusercontent.com/ugc/14936784213521439739/3EA33A8516BDE538B7963F044CD1B7AB4B0BB60D/",
    9467224: "https://cdn.steamusercontent.com/ugc/13052583756685508/22B0338D7E09FB2F021E5DB5BBEFFD170D5E5E1A/",
    9572001: "https://cdn.steamusercontent.com/ugc/10501094611027794535/1569CC553CB72963C8EC4C3F807EE50DA925BDC2/",
    9823272: "https://cdn.steamusercontent.com/ugc/12970505637628494427/B04C3358F4E815ADFC2F8B1B8BE3AB0CE75C8881/",
    9824702: "https://cdn.steamusercontent.com/ugc/11751543457229798134/1569CC553CB72963C8EC4C3F807EE50DA925BDC2/",
    9828897: "https://cdn.steamusercontent.com/ugc/16170413258693955016/5ABDC787F5CF4BBDD603F15933D9F5B0F8EB0D8A/",
    9895392: "https://cdn.steamusercontent.com/ugc/13061694558372404982/7AC363D410AC6F2F4B016EE7D73B7C266D0113F9/",
    9964962: "https://cdn.steamusercontent.com/ugc/13245379764580870318/1048428BEFAC87EC1C64E15706A4758A173B5BFB/",
    10020555: "https://cdn.steamusercontent.com/ugc/11668290585730417471/FB22B7ED74C1C73D4E27C0CBBBF47FC194611231/",
    10081680: "https://cdn.steamusercontent.com/ugc/17521324169419112276/F3F4EBC942578E127594737DB79BF3087A18C1DF/",
    10136357: "https://cdn.steamusercontent.com/ugc/15407628420362751528/49F6005A08A3BB7F21EE77B39EF90872858F8C89/",
    10144195: "https://cdn.steamusercontent.com/ugc/12715064725135883080/A89EE912CE77AC451D6E71FA5FCA0EF3F1EF45E9/",
    10150413: "https://cdn.steamusercontent.com/ugc/13143526280079059732/D5CE25B2DAF10A467D37758AF73C4DCD002AC65E/",
    10150538: "https://cdn.steamusercontent.com/ugc/10055782735581672481/2B2BCEA9CC05286D7164E4548A2EB64CDBC77F31/",
}

REQUIRE_TIER_TOURNAMENT = True
TIER_TOURNAMENT_KEYWORDS = (
    "blast",
    "dreamleague",
    "pgl",
    "the international",
    "ti 20",
    "ewc",
    "esl one",
    "esports world cup",
    "riyadh masters",
    "fissure playground",
    "games of the future",
)

EXCLUDED_TOURNAMENT_KEYWORDS = (
    "qualifier",
    "qualification",
    "closed qualifier",
    "open qualifier",
    "division",
    "academy",
    "regional",
    "showmatch",
)


def is_allowed_tier1_league(league_id: int | str | None = 0, league_name: str | None = "") -> bool:
    try:
        resolved_id = int(league_id or 0)
    except (TypeError, ValueError):
        resolved_id = 0
    if resolved_id in TIER1_LEAGUES:
        return True

    normalized_name = str(league_name or "").strip().lower()
    if not normalized_name:
        return False
    if any(keyword in normalized_name for keyword in EXCLUDED_TOURNAMENT_KEYWORDS):
        return False
    return any(keyword in normalized_name for keyword in TIER_TOURNAMENT_KEYWORDS)


def _read_secret_file(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _read_env_or_file(env_name: str, file_name: str) -> str:
    return (os.getenv(env_name) or _read_secret_file(file_name)).strip()


def _read_channel_id() -> str:
    return (os.getenv("CHANNEL_ID") or DEFAULT_CHANNEL_ID).strip()


CHANNEL_ID = _read_channel_id()
TELEGRAM_TOKEN = _read_env_or_file("TELEGRAM_TOKEN", "telegram_token.txt")
STRATZ_TOKEN = _read_env_or_file("STRATZ_TOKEN", "stratz_token.txt")
STEAM_API_KEY = _read_env_or_file("STEAM_API_KEY", "steam_api_key.txt")
