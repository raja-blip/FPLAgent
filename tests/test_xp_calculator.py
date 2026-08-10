import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import xp_calculator  # noqa: E402
from models import Fixture, Gameweek, Player, Team  # noqa: E402


def make_team(id_, attack_home=1250, attack_away=1250, defence_home=1250, defence_away=1250):
    return Team(
        id=id_, name=f"Team{id_}", short_name=f"T{id_}", strength=4,
        strength_overall_home=1250, strength_overall_away=1250,
        strength_attack_home=attack_home, strength_attack_away=attack_away,
        strength_defence_home=defence_home, strength_defence_away=defence_away,
    )


def make_player(id_, team, element_type=3, form=6.0, xgi=3.0, minutes=450, chance=None, status="a"):
    return Player(
        id=id_, web_name=f"Player{id_}", first_name="F", second_name="L",
        team=team, element_type=element_type, now_cost=80, form=form,
        chance_of_playing_next_round=chance, minutes=minutes,
        expected_goals=xgi * 0.55, expected_assists=xgi * 0.45,
        expected_goal_involvements=xgi, ict_index=100, status=status,
    )


def _next_gw():
    return Gameweek(
        id=1, name="GW1", deadline_time="", deadline_time_epoch=0,
        finished=False, is_current=False, is_next=True,
    )


def test_injured_player_gets_zero_xp(monkeypatch):
    strong_team = make_team(1)
    weak_defence_opp = make_team(2, defence_home=900, defence_away=900)
    injured = make_player(1, team=1, status="i")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=2,
                       team_a_difficulty=4, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [injured])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [strong_team, weak_defence_opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    assert df.iloc[0]["current_gameweek_xP"] == 0.0


def test_in_form_attacker_vs_weak_defence_scores_well(monkeypatch):
    strong_team = make_team(1)
    weak_defence_opp = make_team(2, defence_home=900, defence_away=900)
    striker = make_player(1, team=1, element_type=4, form=8.0, xgi=6.0, minutes=800)
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=2,
                       team_a_difficulty=5, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [striker])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [strong_team, weak_defence_opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    xp = df.iloc[0]["current_gameweek_xP"]
    assert xp > 5.0  # a genuinely in-form striker vs a weak defence should clear a decent bar


def test_rolling_4gw_sums_across_fixtures(monkeypatch):
    team = make_team(1)
    opp = make_team(2)
    player = make_player(1, team=1)
    fixtures = [
        Fixture(id=i, event=gw, team_h=1, team_a=2, team_h_difficulty=3,
                team_a_difficulty=3, kickoff_time=None, finished=False)
        for i, gw in enumerate([1, 2, 3, 4], start=1)
    ]

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: fixtures)
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=4)
    row = df.iloc[0]
    # 4 identical fixtures -> rolling should be ~4x the single-gameweek value
    assert row["rolling_4gw_xP"] == pytest.approx(row["current_gameweek_xP"] * 4, rel=0.01)


def test_clean_sheet_points_differ_by_position(monkeypatch):
    team = make_team(1)
    weak_attack_opp = make_team(2, attack_home=900, attack_away=900)
    gk = make_player(1, team=1, element_type=1, form=4.0, xgi=0.0, minutes=450)
    mid = make_player(2, team=1, element_type=3, form=4.0, xgi=0.0, minutes=450)
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=2,
                       team_a_difficulty=2, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [gk, mid])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, weak_attack_opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    gk_xp = df[df["player_id"] == 1].iloc[0]["current_gameweek_xP"]
    mid_xp = df[df["player_id"] == 2].iloc[0]["current_gameweek_xP"]
    # GK gets 4 clean-sheet points vs MID's 1, with identical everything else
    assert gk_xp > mid_xp


def test_head_to_head_nudge_only_applies_after_a_meeting(monkeypatch):
    team = make_team(1)
    opp = make_team(2)
    player = make_player(1, team=1, form=6.0, xgi=3.0)

    past_meeting = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                            team_a_difficulty=3, kickoff_time=None, finished=True)
    upcoming = Fixture(id=2, event=2, team_h=1, team_a=2, team_h_difficulty=3,
                        team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [past_meeting, upcoming])
    monkeypatch.setattr(
        xp_calculator.fpl_client, "get_next_gameweek",
        lambda: Gameweek(id=2, name="GW2", deadline_time="", deadline_time_epoch=0,
                          finished=False, is_current=False, is_next=True),
    )

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    with_history_xp = df.iloc[0]["current_gameweek_xP"]

    # Same setup, but with the past meeting removed -> nudge should be neutral,
    # producing a slightly lower (or equal) projection.
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [upcoming])
    df_no_history = xp_calculator.build_xp_table(horizon_gameweeks=1)
    without_history_xp = df_no_history.iloc[0]["current_gameweek_xP"]

    assert with_history_xp >= without_history_xp
