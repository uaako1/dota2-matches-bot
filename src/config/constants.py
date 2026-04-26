from __future__ import annotations

try:
    from config import TIER1_LEAGUES as LEGACY_TIER1_LEAGUES
except Exception:
    LEGACY_TIER1_LEAGUES = {}

TIER1_LEAGUES = dict(LEGACY_TIER1_LEAGUES)
