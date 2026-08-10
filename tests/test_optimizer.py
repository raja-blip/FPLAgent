import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import optimizer  # noqa: E402


def _pool_row(pid, position, team, price, xp):
    return {
        "player_id": pid,
        "web_name": f"P{pid}",
        "position": position,
        "team": team,
        "price": price,
        "current_gameweek_xP": xp,
        "rolling_4gw_xP": xp * 4,
    }


def make_basic_pool():
    """A pool with just enough depth per position/team to be feasible."""
    rows = []
    pid = 1
    for team in range(1, 5):  # 4 GK across 4 teams
        rows.append(_pool_row(pid, 1, team, 4.5, 3.0))
        pid += 1
    for team in range(1, 6):  # 10 DEF across 5 teams (2 each)
        for _ in range(2):
            rows.append(_pool_row(pid, 2, team, 4.5, 3.5))
            pid += 1
    for team in range(1, 6):  # 10 MID across 5 teams (2 each)
        for _ in range(2):
            rows.append(_pool_row(pid, 3, team, 5.5, 4.0))
            pid += 1
    for team in range(1, 4):  # 6 FWD across 3 teams (2 each)
        for _ in range(2):
            rows.append(_pool_row(pid, 4, team, 6.0, 4.5))
            pid += 1
    return pd.DataFrame(rows)


def test_select_squad_respects_all_constraints():
    pool = make_basic_pool()
    result = optimizer.select_squad(pool, budget=100.0)

    assert len(result.squad_ids) == 15
    squad = pool[pool["player_id"].isin(result.squad_ids)]

    assert (squad["position"] == 1).sum() == 2
    assert (squad["position"] == 2).sum() == 5
    assert (squad["position"] == 3).sum() == 5
    assert (squad["position"] == 4).sum() == 3
    assert squad["price"].sum() <= 100.0
    assert squad.groupby("team").size().max() <= 3


def test_transfer_uses_free_transfer_for_clear_upgrade():
    pool = make_basic_pool()
    initial = optimizer.select_squad(pool, budget=100.0)

    standout = _pool_row(999, 3, 9, 5.5, 9.0)  # MID, new team, big xP jump
    pool_with_standout = pd.concat([pool, pd.DataFrame([standout])], ignore_index=True)

    result = optimizer.select_squad(
        pool_with_standout,
        budget=100.0,
        existing_squad_ids=initial.squad_ids,
        free_transfers=1,
    )

    assert 999 in result.transfers_in
    assert result.hits_taken == 0  # one clear upgrade fits inside 1 free transfer


def test_transfer_takes_hit_when_gain_outweighs_cost():
    pool = make_basic_pool()
    initial = optimizer.select_squad(pool, budget=100.0)

    standout_1 = _pool_row(998, 3, 9, 5.5, 9.0)
    standout_2 = _pool_row(997, 2, 9, 4.5, 8.0)
    pool_with_standouts = pd.concat(
        [pool, pd.DataFrame([standout_1, standout_2])], ignore_index=True
    )

    result = optimizer.select_squad(
        pool_with_standouts,
        budget=100.0,
        existing_squad_ids=initial.squad_ids,
        free_transfers=1,
    )

    assert 998 in result.transfers_in
    assert 997 in result.transfers_in
    assert result.hits_taken == 1
    assert result.hit_cost == 4


def test_starting_xi_respects_formation_rules():
    pool = make_basic_pool()
    squad_result = optimizer.select_squad(pool, budget=100.0)
    lineup = optimizer.select_starting_xi(squad_result.squad_ids, pool)

    assert len(lineup.starting_ids) == 11
    assert len(lineup.bench_ids) == 4
    starting = pool[pool["player_id"].isin(lineup.starting_ids)]
    assert (starting["position"] == 1).sum() == 1
    assert (starting["position"] == 2).sum() >= 3
    assert (starting["position"] == 3).sum() >= 2
    assert (starting["position"] == 4).sum() >= 1
    assert lineup.captain_id in lineup.starting_ids
    assert lineup.vice_captain_id in lineup.starting_ids
    assert lineup.captain_id != lineup.vice_captain_id


def test_captain_prefers_attacker_among_top_candidates():
    # Player 4 (DEF) has the single highest raw xP; player 6 (MID) is a
    # close second. Captain should go to the attacker, not the higher-xP
    # defender, per the ceiling-leaning heuristic.
    rows = [
        _pool_row(1, 1, 1, 4.5, 3.0),
        _pool_row(2, 2, 1, 4.5, 3.0),
        _pool_row(3, 2, 2, 4.5, 3.0),
        _pool_row(4, 2, 3, 4.5, 6.2),
        _pool_row(5, 2, 4, 4.5, 3.0),
        _pool_row(6, 3, 1, 5.5, 6.0),
        _pool_row(7, 3, 2, 5.5, 3.0),
        _pool_row(8, 3, 3, 5.5, 3.0),
        _pool_row(9, 3, 4, 5.5, 3.0),
        _pool_row(10, 3, 5, 5.5, 3.0),
        _pool_row(11, 4, 1, 6.0, 3.0),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(starting_ids, by_id, "current_gameweek_xP")

    assert captain_id == 6
    assert vice_id != captain_id
