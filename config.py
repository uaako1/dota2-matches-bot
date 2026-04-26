import os
from pathlib import Path

# ===== Bot settings =====
DEFAULT_CHANNEL_ID = "@dota2_matches"
DEFAULT_STREAM_URL = os.getenv("DEFAULT_STREAM_URL", "https://www.twitch.tv/dota2_paragon_ru").strip()

CHECK_INTERVAL_MINUTES = 2
MAX_MATCHES_PER_CHECK = 10
POST_DELAY_SECONDS = 1
LIVE_CHECK_ENABLED = True
LIVE_ANNOUNCE_ENABLED = True
ACTIVE_LEAGUE_LOOKBACK_DAYS = 45

STATE_FILE = os.getenv("STATE_FILE", "data/bot_state.json").strip()

# Strict tier-1/main-event league IDs. No Division 2, no qualifiers, no minor leagues.
TIER1_LEAGUES = {
    18324: "The International 2025",
    16935: "The International 2024",
    19422: "ESL One Birmingham 2026",
    17795: "ESL One Raleigh 2025",
    19099: "BLAST Slam VI",
    17414: "BLAST Slam I",
    19543: "PGL Wallachia 2026 Season 8",
    19435: "PGL Wallachia 2026 Season 7",
    18920: "PGL Wallachia 2025 Season 6",
    18358: "PGL Wallachia 2025 Season 5",
    18058: "PGL Wallachia 2025 Season 4",
    19269: "DreamLeague Season 28",
    18988: "DreamLeague Season 27",
    18111: "DreamLeague Season 26",
    17765: "DreamLeague Season 25",
    18863: "FISSURE PLAYGROUND 2",
    16881: "Riyadh Masters 2024 at Esports World Cup",
}

ALLOWED_LEAGUE_IDS = set(TIER1_LEAGUES)
LEAGUE_NAMES = dict(TIER1_LEAGUES)

REQUIRE_TIER_TOURNAMENT = True
TIER_TOURNAMENT_KEYWORDS = (
    "blast",
    "dreamleague",
    "pgl",
    "the international",
    "ti 20",
    "esl one",
    "esports world cup",
    "riyadh masters",
    "fissure playground",
)


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
