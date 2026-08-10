"""Data models for the subset of FPL fields this agent actually uses.

The real bootstrap-static payload has 60+ fields per player — we only
declare the ones the xP model and optimizer will need. Pydantic's default
(non-strict) mode coerces the numeric-strings the FPL API sometimes
returns (e.g. "6.5") into floats automatically.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class Team(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    short_name: str
    # These can be null early in a season (e.g. for newly-promoted teams
    # or before FPL has enough data to calculate them) — the live API
    # doesn't guarantee these are always populated, even though it
    # looked that way from documentation and earlier-season examples.
    strength: Optional[int] = None
    strength_overall_home: Optional[int] = None
    strength_overall_away: Optional[int] = None
    strength_attack_home: Optional[int] = None
    strength_attack_away: Optional[int] = None
    strength_defence_home: Optional[int] = None
    strength_defence_away: Optional[int] = None


class Gameweek(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    deadline_time: str
    deadline_time_epoch: int
    finished: bool
    is_current: bool
    is_next: bool


class Player(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    web_name: str
    first_name: str
    second_name: str
    team: int
    element_type: int  # 1=GK, 2=DEF, 3=MID, 4=FWD
    now_cost: int  # tenths of a million, e.g. 100 -> £10.0m
    form: float = 0.0
    chance_of_playing_next_round: Optional[int] = None
    minutes: int = 0
    expected_goals: float = 0.0
    expected_assists: float = 0.0
    expected_goal_involvements: float = 0.0
    ict_index: float = 0.0
    status: str = "a"  # a=available, d=doubtful, i=injured, s=suspended, u=unavailable

    @property
    def price(self) -> float:
        return self.now_cost / 10


class Fixture(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    event: Optional[int]
    team_h: int
    team_a: int
    team_h_difficulty: int
    team_a_difficulty: int
    kickoff_time: Optional[str]
    finished: bool
