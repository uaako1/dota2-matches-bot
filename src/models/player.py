from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlayerModel:
    account_id: int = 0
    name: str = ""
    hero_id: int = 0
    hero_name: str = ""
    hero_short_name: str = ""
    is_radiant: bool = False
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    gold_per_min: int = 0
    xp_per_min: int = 0
    net_worth: int = 0
    hero_damage: int = 0
    hero_healing: int = 0
    tower_damage: int = 0
    items: list[dict] = field(default_factory=list)
    backpack: list[dict] = field(default_factory=list)
    buffs: list[dict] = field(default_factory=list)
    neutral_item: dict | None = None
    additional_units: list[dict] = field(default_factory=list)
