"""
Squad optimizer using Mixed-Integer Linear Programming (pulp).

Builds a full 15-man squad (or evolves an existing one via transfers)
under FPL's real constraints, then picks the best starting XI, captain,
and vice-captain from that squad.

Handles both "build me a squad from scratch" (no existing squad) and
"here's my current squad, what transfers should I make" (existing squad
given) with the same underlying optimization — a transfer is just "sell
player X, buy player Y", and making more transfers than you have free
costs 4 points each, which the solver weighs directly against the
expected-points gain in one objective function. Per our agreed rule
there's no minimum-gain threshold on free transfers, and hits get taken
whenever the expected gain outweighs the -4 cost — both fall out
naturally from the objective, nothing hardcoded to force either.

Known simplification: sell price uses each player's current listed
price, not FPL's actual sell-value mechanic (a 50% sell-on fee applies
to price rises since you bought a player). Fine for Phase 3 — worth
refining once we're pulling your actual squad/bank balance in Phase 4.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pulp

SQUAD_SIZE = 15
POSITION_COUNTS = {1: 2, 2: 5, 3: 5, 4: 3}  # GK, DEF, MID, FWD
MAX_PER_TEAM = 3
STARTING_XI_SIZE = 11
MIN_STARTING = {1: 1, 2: 3, 3: 2, 4: 1}  # minimum per position in starting XI
HIT_COST = 4


@dataclass
class SquadResult:
    squad_ids: list[int]
    transfers_in: list[int]
    transfers_out: list[int]
    hits_taken: int
    hit_cost: float
    projected_xp: float


@dataclass
class LineupResult:
    starting_ids: list[int]
    bench_ids: list[int]  # ordered, bench_ids[0] = first sub
    captain_id: int
    vice_captain_id: int


def select_squad(
    xp_df: pd.DataFrame,
    budget: float = 100.0,
    existing_squad_ids: list[int] | None = None,
    free_transfers: int = 1,
    xp_column: str = "rolling_4gw_xP",
    hit_margin: float = 0.0,
) -> SquadResult:
    """Pick the 15-man squad maximizing rolling xP minus hit cost.

    existing_squad_ids=None -> from-scratch build (e.g. pre-season), no
    transfer penalty. Existing squad given -> the weekly transfer decision.

    hit_margin: added on top of the real -4 hit cost when DECIDING
    whether a hit is worth taking, without changing the actual points
    charged (that's still exactly -4, the real FPL rule — hit_cost on
    SquadResult always reflects the true cost).

    Added after a real backtest found "take a hit whenever the
    projected gain exceeds the -4 cost, however slim" led to 127 hits
    across one season, costing 508 points overall — the model isn't
    precise enough to trust a razor-thin edge, and small apparent gains
    in a noisy weekly estimate were triggering real, expensive,
    net-negative reshuffling no real manager would do. This only
    affects HITS — a genuinely free transfer still has zero reason to
    require any margin, since it costs nothing either way.
    """
    players = xp_df.to_dict("records")
    ids = [p["player_id"] for p in players]
    by_id = {p["player_id"]: p for p in players}

    prob = pulp.LpProblem("squad_selection", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in ids}

    prob += pulp.lpSum(x[i] for i in ids) == SQUAD_SIZE
    for pos, count in POSITION_COUNTS.items():
        prob += pulp.lpSum(x[i] for i in ids if by_id[i]["position"] == pos) == count

    teams = {by_id[i]["team"] for i in ids}
    for team in teams:
        prob += pulp.lpSum(x[i] for i in ids if by_id[i]["team"] == team) <= MAX_PER_TEAM

    prob += pulp.lpSum(x[i] * by_id[i]["price"] for i in ids) <= budget

    objective = pulp.lpSum(x[i] * by_id[i][xp_column] for i in ids)

    if existing_squad_ids:
        existing = [i for i in existing_squad_ids if i in x]
        transfers_made = pulp.lpSum((1 - x[i]) for i in existing)
        hits = pulp.LpVariable("hits", lowBound=0)
        prob += hits >= transfers_made - free_transfers
        # Real cost charged is still exactly HIT_COST (4) — hit_margin
        # only raises the bar the OPTIMIZER must clear to choose a hit,
        # not what actually gets deducted from the final score.
        objective -= (HIT_COST + hit_margin) * hits

    prob += objective
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Optimizer did not find an optimal solution: {pulp.LpStatus[prob.status]}")

    selected = [i for i in ids if x[i].value() == 1]
    projected = sum(by_id[i][xp_column] for i in selected)

    transfers_in: list[int] = []
    transfers_out: list[int] = []
    hits_taken = 0
    hit_cost = 0.0
    if existing_squad_ids:
        existing_set = set(existing_squad_ids)
        new_set = set(selected)
        transfers_out = sorted(existing_set - new_set)
        transfers_in = sorted(new_set - existing_set)
        hits_taken = max(0, len(transfers_out) - free_transfers)
        hit_cost = hits_taken * HIT_COST
        projected -= hit_cost

    return SquadResult(
        squad_ids=selected,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        hits_taken=hits_taken,
        hit_cost=hit_cost,
        projected_xp=round(projected, 2),
    )


def select_starting_xi(
    squad_ids: list[int],
    xp_df: pd.DataFrame,
    xp_column: str = "current_gameweek_xP",
) -> LineupResult:
    """From a 15-man squad, pick the best valid starting XI, bench order, captain, and vice."""
    squad_df = xp_df[xp_df["player_id"].isin(squad_ids)]
    by_id = {row["player_id"]: row for row in squad_df.to_dict("records")}
    ids = list(by_id.keys())

    prob = pulp.LpProblem("lineup_selection", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"start_{i}", cat="Binary") for i in ids}

    prob += pulp.lpSum(x[i] for i in ids) == STARTING_XI_SIZE
    for pos, min_count in MIN_STARTING.items():
        prob += pulp.lpSum(x[i] for i in ids if by_id[i]["position"] == pos) >= min_count
    prob += pulp.lpSum(x[i] for i in ids if by_id[i]["position"] == 1) == 1  # exactly 1 starting GK

    prob += pulp.lpSum(x[i] * by_id[i][xp_column] for i in ids)
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Lineup optimizer failed: {pulp.LpStatus[prob.status]}")

    starting_ids = [i for i in ids if x[i].value() == 1]
    bench_ids = sorted(
        (i for i in ids if i not in starting_ids),
        key=lambda i: by_id[i][xp_column],
        reverse=True,
    )

    captain_id, vice_captain_id = _pick_captain(starting_ids, by_id, xp_column)

    return LineupResult(
        starting_ids=starting_ids,
        bench_ids=bench_ids,
        captain_id=captain_id,
        vice_captain_id=vice_captain_id,
    )


def _pick_captain(
    starting_ids: list[int], by_id: dict[int, dict], xp_column: str
) -> tuple[int, int]:
    """Captain the single highest-projected scorer in the starting XI.

    This used to prefer an attacking position among the top 3 by xP, on
    the theory that goal involvements give more ceiling than a
    clean-sheet-driven defender/keeper score. A real 38-gameweek
    backtest against the 2025/26 season found that heuristic actually
    cost 33 points over the season — real weeks existed where a
    defender or goalkeeper had the outright highest projection (a big
    clean-sheet-plus-bonus haul) and the attacker-preference rule
    overrode that for a lower-scoring attacker. Tested against a
    trend-aware alternative too (blending in the 4-week rolling
    projection); this simple version still won. Simplicity beat both
    more elaborate versions on real, measured results — not a guess.
    """
    ranked = sorted(starting_ids, key=lambda i: by_id[i][xp_column], reverse=True)
    return ranked[0], ranked[1]
