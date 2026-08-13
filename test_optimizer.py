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


def test_hit_margin_suppresses_marginal_hit_a_zero_margin_would_take():
    # Reproduces the real backtest finding: a hit that clears the bare
    # -4 cost by only a slim margin should NOT be taken once hit_margin
    # demands a bigger edge — this is what actually fixes the 127-hit,
    # 508-point season found in the real backtest.
    pool = make_basic_pool()
    initial = optimizer.select_squad(pool, budget=100.0)

    # A marginal upgrade: existing MIDs score rolling_4gw_xP=16.0 (raw
    # xp 4.0 x4). A raw xp of 5.075 -> rolling_4gw_xP=20.3, a gain of
    # 4.3 -- just barely clears the bare -4 hit cost (net +0.3) at zero
    # margin, but falls well short of an 8-point margin requirement.
    marginal_upgrade = _pool_row(996, 3, 9, 5.5, 5.075)
    pool_with_marginal = pd.concat([pool, pd.DataFrame([marginal_upgrade])], ignore_index=True)

    result_no_margin = optimizer.select_squad(
        pool_with_marginal, budget=100.0,
        existing_squad_ids=initial.squad_ids, free_transfers=0, hit_margin=0.0,
    )
    result_with_margin = optimizer.select_squad(
        pool_with_marginal, budget=100.0,
        existing_squad_ids=initial.squad_ids, free_transfers=0, hit_margin=8.0,
    )

    assert 996 in result_no_margin.transfers_in  # zero margin takes the marginal hit
    assert 996 not in result_with_margin.transfers_in  # real margin correctly refuses it
    assert result_with_margin.hits_taken == 0


def test_hit_margin_does_not_affect_free_transfers():
    # The margin should only raise the bar for HITS — a genuinely free
    # transfer has no reason to require extra margin, since it costs
    # nothing either way.
    pool = make_basic_pool()
    initial = optimizer.select_squad(pool, budget=100.0)

    standout = _pool_row(999, 3, 9, 5.5, 9.0)
    pool_with_standout = pd.concat([pool, pd.DataFrame([standout])], ignore_index=True)

    result = optimizer.select_squad(
        pool_with_standout, budget=100.0,
        existing_squad_ids=initial.squad_ids, free_transfers=1, hit_margin=8.0,
    )

    assert 999 in result.transfers_in  # a free transfer, unaffected by hit_margin
    assert result.hits_taken == 0


def test_max_player_price_excludes_expensive_players_from_selection():
    pool = make_basic_pool()
    mega_premium = _pool_row(995, 4, 9, 15.5, 9.5)  # by far the best player, but very expensive
    pool_with_premium = pd.concat([pool, pd.DataFrame([mega_premium])], ignore_index=True)

    result_no_cap = optimizer.select_squad(pool_with_premium, budget=100.0)
    assert 995 in result_no_cap.squad_ids  # no cap -> the optimizer happily buys the best player

    result_with_cap = optimizer.select_squad(pool_with_premium, budget=100.0, max_player_price=13.0)
    assert 995 not in result_with_cap.squad_ids  # capped -> excluded regardless of quality


def test_max_player_price_correctly_counts_selling_an_owned_expensive_player_as_a_transfer():
    # The real bug this test guards against: if a price cap is applied
    # to an EXISTING squad that already owns an expensive player, that
    # player must still be correctly counted as "sold" (a real
    # transfer/hit), not silently dropped from the accounting because
    # they were filtered out of the candidate pool.
    pool = make_basic_pool()
    mega_premium = _pool_row(995, 4, 9, 15.5, 9.5)
    pool_with_premium = pd.concat([pool, pd.DataFrame([mega_premium])], ignore_index=True)

    # Squad that owns the mega-premium (built with no cap).
    initial = optimizer.select_squad(pool_with_premium, budget=100.0)
    assert 995 in initial.squad_ids

    # Now apply the cap on the SAME squad with 0 free transfers -- the
    # forced sale of 995 must show up as a real transfer_out and a hit.
    result = optimizer.select_squad(
        pool_with_premium, budget=100.0,
        existing_squad_ids=initial.squad_ids, free_transfers=0,
        max_player_price=13.0,
    )

    assert 995 in result.transfers_out  # correctly counted as sold
    assert 995 not in result.squad_ids
    assert result.hits_taken >= 1  # forcing the sale cost a real hit, correctly accounted for


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


def test_gk_and_def_are_never_eligible_for_captain():
    # Player 4 (DEF) has the single highest raw xP in the whole XI —
    # under the old logic this would win captaincy outright. Under the
    # new hard rule, GK/DEF are never eligible regardless of xP, so
    # captaincy must go to player 6 (MID), the highest among eligible
    # players, even though its xP is lower.
    rows = [
        _pool_row(1, 1, 1, 4.5, 3.0),
        _pool_row(2, 2, 1, 4.5, 3.0),
        _pool_row(3, 2, 2, 4.5, 3.0),
        _pool_row(4, 2, 3, 4.5, 6.2),  # DEF, highest raw xP in the XI
        _pool_row(5, 2, 4, 4.5, 3.0),
        _pool_row(6, 3, 1, 5.5, 6.0),  # MID, highest among ELIGIBLE
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

    assert captain_id == 6  # highest-xP ELIGIBLE player — DEF excluded despite higher raw xP
    assert vice_id == 7  # second-highest ELIGIBLE (tie-break preserves list order among 3.0 scorers)
    assert by_id[vice_id]["position"] in (3, 4)  # vice must also come from the eligible pool
    assert vice_id != captain_id


def test_reproduces_the_real_bug_goalkeeper_never_wins_captain():
    # Direct reproduction of what the backtest actually found: Kelleher
    # (GK) had the single highest projection for 4 straight gameweeks
    # and was wrongly captained. Even with an enormous GK score, a much
    # lower FWD/MID score must still win.
    rows = [
        _pool_row(1, 1, 1, 4.5, 15.0),  # GK, huge week, must never be eligible
        _pool_row(2, 2, 1, 6.0, 12.0),  # DEF, also huge, also never eligible
        _pool_row(3, 4, 1, 8.0, 3.0),   # FWD, modest week
        _pool_row(4, 3, 1, 6.0, 2.5),   # MID, modest week
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(starting_ids, by_id, "current_gameweek_xP")

    assert captain_id == 3  # the FWD, despite scoring far less than GK/DEF that week
    assert vice_id == 4


def test_captain_vice_are_the_top_two_by_projection():
    rows = [
        _pool_row(1, 1, 1, 4.5, 2.0),
        _pool_row(2, 3, 1, 5.5, 9.0),
        _pool_row(3, 4, 1, 6.0, 8.5),
        _pool_row(4, 2, 1, 4.5, 3.0),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(starting_ids, by_id, "current_gameweek_xP")

    assert captain_id == 2
    assert vice_id == 3


def test_captain_stays_with_incumbent_when_challenger_edge_is_marginal():
    # Real evidence for this: the 2024/25 world champion captained the
    # same player (Salah) 23 times across the season. A 0.3-point edge
    # for a challenger shouldn't flip the armband every week.
    rows = [
        _pool_row(1, 3, 1, 9.0, 8.0),   # incumbent captain, close second
        _pool_row(2, 3, 2, 9.0, 8.3),   # challenger, marginal edge
        _pool_row(3, 2, 1, 4.5, 3.0),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(
        starting_ids, by_id, "current_gameweek_xP",
        incumbent_captain_id=1, switch_margin=2.0,
    )

    assert captain_id == 1  # incumbent kept, edge (0.3) didn't clear the margin
    assert vice_id == 2  # challenger becomes vice instead


def test_captain_switches_when_challenger_edge_clears_margin():
    rows = [
        _pool_row(1, 3, 1, 9.0, 4.0),   # incumbent captain, now out of form
        _pool_row(2, 3, 2, 9.0, 9.0),   # challenger, huge edge
        _pool_row(3, 2, 1, 4.5, 3.0),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(
        starting_ids, by_id, "current_gameweek_xP",
        incumbent_captain_id=1, switch_margin=2.0,
    )

    assert captain_id == 2  # edge (5.0) clears the margin -> real switch
    assert vice_id == 1


def test_captain_stickiness_has_no_effect_with_no_incumbent():
    # First-ever gameweek, or no prior captain tracked -> behaves
    # exactly like the plain top-1 logic.
    rows = [
        _pool_row(1, 3, 1, 9.0, 8.0),
        _pool_row(2, 3, 2, 9.0, 8.3),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(
        starting_ids, by_id, "current_gameweek_xP",
        incumbent_captain_id=None, switch_margin=2.0,
    )

    assert captain_id == 2  # plain top-1, no stickiness applied
    assert vice_id == 1


def test_captain_stickiness_ignores_incumbent_no_longer_starting():
    # Incumbent captain was sold/benched -> can't stay captain, no
    # crash, falls back to plain top-1 among the current starting XI.
    rows = [
        _pool_row(2, 3, 2, 9.0, 8.3),
        _pool_row(3, 4, 1, 6.0, 3.0),
    ]
    df = pd.DataFrame(rows)
    starting_ids = df["player_id"].tolist()
    by_id = {row["player_id"]: row for row in df.to_dict("records")}

    captain_id, vice_id = optimizer._pick_captain(
        starting_ids, by_id, "current_gameweek_xP",
        incumbent_captain_id=1, switch_margin=2.0,  # 1 isn't in starting_ids anymore
    )

    assert captain_id == 2
    assert vice_id == 3
