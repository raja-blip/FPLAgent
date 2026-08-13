"""
Shared state for the T-24h propose / T-3h execute loop.

Why this exists: the two scripts run as completely separate GitHub
Actions jobs, hours apart, on brand-new throwaway runners each time —
nothing is "remembered" between them unless we persist it somewhere.
The chosen mechanism: a plain JSON file at STATE_PATH, committed back
to the repo by the workflow itself after each run (see the .yml files
— this module only handles the read/write, not the git mechanics).

What needs to survive between runs:
  - The season-long hit budget used so far (for max_hits_remaining)
  - The chip plan for the rest of the season (built once, reused)
  - Each gameweek's T-24h proposal — what was proposed, when, and
    whether it's since been executed — so T-3h knows what to compare
    against and what to actually submit.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_PATH = Path(__file__).parent / "state" / "agent_state.json"

DEFAULT_STATE: dict[str, Any] = {
    "season_hits_used": 0,
    "chip_plan": None,  # filled in by chip_strategy.build_chip_plan, cached here
    "gameweeks": {},  # keyed by str(gameweek_id), see propose.py for the shape
}


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return json.loads(json.dumps(DEFAULT_STATE))  # deep copy
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True, parents=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_gameweek_record(state: dict[str, Any], gameweek_id: int) -> dict[str, Any] | None:
    return state["gameweeks"].get(str(gameweek_id))


def set_gameweek_record(state: dict[str, Any], gameweek_id: int, record: dict[str, Any]) -> None:
    state["gameweeks"][str(gameweek_id)] = record
