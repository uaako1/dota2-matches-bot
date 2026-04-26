from __future__ import annotations

from dataclasses import dataclass, field

from src.models.player import PlayerModel


@dataclass(slots=True)
class MatchModel:
    match_id: int
    league_id: int = 0
    league_name: str = ""
    radiant_name: str = "Radiant"
    dire_name: str = "Dire"
    radiant_logo_url: str = ""
    dire_logo_url: str = ""
    radiant_score: int = 0
    dire_score: int = 0
    duration: int = 0
    radiant_win: bool | None = None
    players: list[PlayerModel] = field(default_factory=list)
    bans: list[dict] = field(default_factory=list)
