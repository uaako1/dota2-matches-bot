from __future__ import annotations

try:
    from config import TIER1_LEAGUES as LEGACY_TIER1_LEAGUES
    from config import is_allowed_tier1_league as legacy_is_allowed_tier1_league
except Exception:
    LEGACY_TIER1_LEAGUES = {}

    def legacy_is_allowed_tier1_league(league_id: int | str | None = 0, league_name: str | None = "") -> bool:
        return False

TIER1_LEAGUES = dict(LEGACY_TIER1_LEAGUES)
is_allowed_tier1_league = legacy_is_allowed_tier1_league
