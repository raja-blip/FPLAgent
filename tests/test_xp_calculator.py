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
        expected_goal_involvements=xgi, expected_goal_involvements_per_90=xgi,
        ict_index=100, status=status,
    )


def _next_gw():
    return Gameweek(
        id=1, name="GW1", deadline_time="", deadline_time_epoch=0,
        finished=False, is_current=False, is_next=True,
    )


@pytest.fixture(autouse=True)
def _default_last_season_rates(monkeypatch):
    # Safe default for every test: no last-season data, so existing tests
    # (whose players all have minutes >= 270, past the phase-in point)
    # behave exactly as before. Tests that care about the fallback itself
    # override this within their own body.
    monkeypatch.setattr(xp_calculator.fpl_client, "get_last_season_rates", lambda: {})


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


def test_handles_null_team_strength_from_live_api(monkeypatch):
    # This exact shape broke in production: a real team from the live API
    # with null strength fields (early-season / newly-promoted team with
    # no data yet). Must not crash, and should fall back to a neutral
    # (non-zero) projection rather than erroring out.
    team = Team(id=1, name="Team1", short_name="T1", strength=None,
                strength_overall_home=None, strength_overall_away=None,
                strength_attack_home=None, strength_attack_away=None,
                strength_defence_home=None, strength_defence_away=None)
    opponent = Team(id=2, name="Team2", short_name="T2", strength=None,
                     strength_overall_home=None, strength_overall_away=None,
                     strength_attack_home=None, strength_attack_away=None,
                     strength_defence_home=None, strength_defence_away=None)
    player = make_player(1, team=1, form=6.0, xgi=3.0)
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opponent])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    assert df.iloc[0]["current_gameweek_xP"] > 0


def test_manual_override_boosts_attack_against_weakened_defence(monkeypatch):
    # A team explicitly flagged as defensively weaker than its FPL rating
    # should give attacking players a bigger boost, whether or not FPL's
    # own numbers exist yet.
    team = make_team(1)
    opponent = make_team(2, defence_home=1200, defence_away=1200)  # league-average rating
    player = make_player(1, team=1, form=6.0, xgi=3.0)
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opponent])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    baseline_xp = df.iloc[0]["current_gameweek_xP"]

    monkeypatch.setitem(xp_calculator.TEAM_OVERRIDES, "Team2", {"defence": 0.85})
    df_overridden = xp_calculator.build_xp_table(horizon_gameweeks=1)
    overridden_xp = df_overridden.iloc[0]["current_gameweek_xP"]

    assert overridden_xp > baseline_xp
    xp_calculator.TEAM_OVERRIDES.pop("Team2", None)  # clean up for other tests


def test_manual_override_works_even_when_fpl_data_is_null(monkeypatch):
    # The override should still apply a real signal even when there's no
    # FPL strength number at all to multiply against — this is exactly
    # the pre-season case that motivated building it.
    team = make_team(1)
    opponent = Team(id=2, name="Team2", short_name="T2", strength=None,
                     strength_overall_home=None, strength_overall_away=None,
                     strength_attack_home=None, strength_attack_away=None,
                     strength_defence_home=None, strength_defence_away=None)
    player = make_player(1, team=1, form=6.0, xgi=3.0)
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opponent])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df_neutral = xp_calculator.build_xp_table(horizon_gameweeks=1)
    neutral_xp = df_neutral.iloc[0]["current_gameweek_xP"]

    monkeypatch.setitem(xp_calculator.TEAM_OVERRIDES, "Team2", {"defence": 0.85})
    df_overridden = xp_calculator.build_xp_table(horizon_gameweeks=1)
    overridden_xp = df_overridden.iloc[0]["current_gameweek_xP"]

    assert overridden_xp > neutral_xp
    xp_calculator.TEAM_OVERRIDES.pop("Team2", None)


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


def test_uses_last_season_rate_when_no_current_season_minutes(monkeypatch):
    # Pre-season: 0 current-season minutes, current-season per-90 is 0 too
    # (nothing played yet). Without a last-season fallback, this player
    # would project as worthless -- with it, they should score meaningfully.
    team = make_team(1)
    opp = make_team(2)
    player = make_player(1, team=1, form=0.0, xgi=0.0, minutes=0, status="a")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [player])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)
    monkeypatch.setattr(
        xp_calculator.fpl_client, "get_last_season_rates", lambda: {1: {"egi_per_90": 0.5, "bonus_per_90": 0.0}}
    )

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    with_fallback_xp = df.iloc[0]["current_gameweek_xP"]

    monkeypatch.setattr(xp_calculator.fpl_client, "get_last_season_rates", lambda: {})
    df_no_fallback = xp_calculator.build_xp_table(horizon_gameweeks=1)
    without_fallback_xp = df_no_fallback.iloc[0]["current_gameweek_xP"]

    assert with_fallback_xp > without_fallback_xp


def test_class_player_floor_rescues_a_slumping_player(monkeypatch):
    # Direct test of the "form is temporary, class is permanent"
    # mechanism: a class-list player with genuinely poor underlying
    # numbers this week should still score at least their floor.
    # CLASS_PLAYERS is empty by default (Raj's decision, after
    # backtesting found it net-negative combined with the price cap —
    # see class_players.py) — this test sets its own entry so the
    # mechanism itself stays covered regardless of that live config.
    import xp_calculator as xpc
    monkeypatch.setitem(xpc.CLASS_PLAYERS, "Saka", 5.0)

    team = make_team(1)
    opp = make_team(2)
    slumping_saka = make_player(1, team=1, form=0.5, xgi=0.05, minutes=450, status="a")
    monkeypatch.setattr(slumping_saka, "web_name", "Saka")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [slumping_saka])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    xp = df.iloc[0]["current_gameweek_xP"]

    assert xp >= 5.0


def test_class_player_floor_does_not_apply_when_injured(monkeypatch):
    # The floor must never rescue a player who genuinely isn't playing
    # at all — a slump is not the same thing as unavailability.
    team = make_team(1)
    opp = make_team(2)
    injured_saka = make_player(1, team=1, form=8.0, xgi=5.0, minutes=450, status="i")
    monkeypatch.setattr(injured_saka, "web_name", "Saka")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [injured_saka])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    xp = df.iloc[0]["current_gameweek_xP"]

    assert xp == 0.0  # injured -> 0, floor does not apply


def test_class_player_floor_does_not_lower_a_genuinely_great_week(monkeypatch):
    # The floor is a MINIMUM, not a cap — a class player having a
    # genuinely great week should keep their real (higher) projection.
    import xp_calculator as xpc
    monkeypatch.setitem(xpc.CLASS_PLAYERS, "Saka", 5.0)

    team = make_team(1)
    opp = make_team(2)
    on_fire_saka = make_player(1, team=1, form=9.5, xgi=8.0, minutes=450, status="a")
    monkeypatch.setattr(on_fire_saka, "web_name", "Saka")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [on_fire_saka])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    xp = df.iloc[0]["current_gameweek_xP"]

    assert xp > 5.0  # real projection kept, not capped down to the floor


def test_class_player_floor_does_not_apply_to_unlisted_players(monkeypatch):
    import xp_calculator as xpc
    monkeypatch.setitem(xpc.CLASS_PLAYERS, "Saka", 5.0)

    team = make_team(1)
    opp = make_team(2)
    slumping_nobody = make_player(1, team=1, form=0.5, xgi=0.05, minutes=450, status="a")
    monkeypatch.setattr(slumping_nobody, "web_name", "SomeRandomPlayer")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [slumping_nobody])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    xp = df.iloc[0]["current_gameweek_xP"]

    assert xp < 5.0  # not on the list -> no floor rescue


def test_phases_out_last_season_rate_as_current_minutes_accumulate(monkeypatch):
    # Same last-season rate, but one player has 0 current-season minutes
    # and another has played a full season's worth (way past the 270-min
    # phase-in point) with a much lower current per-90 rate. The
    # well-established player should lean on their OWN current output,
    # not still be dragged toward last season's number.
    team = make_team(1)
    opp = make_team(2)
    fresh_player = make_player(2, team=1, form=0.0, xgi=0.0, minutes=0, chance=100, status="a")
    established_player = make_player(
        3, team=1, form=1.0, xgi=0.1, minutes=2000, chance=100, status="a"
    )
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(
        xp_calculator.fpl_client, "get_players", lambda: [fresh_player, established_player]
    )
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)
    # Both players share the same (high) last-season rate.
    monkeypatch.setattr(
        xp_calculator.fpl_client,
        "get_last_season_rates",
        lambda: {2: {"egi_per_90": 0.8, "bonus_per_90": 0.0}, 3: {"egi_per_90": 0.8, "bonus_per_90": 0.0}},
    )

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    fresh_xp = df[df["player_id"] == 2].iloc[0]["current_gameweek_xP"]
    established_xp = df[df["player_id"] == 3].iloc[0]["current_gameweek_xP"]

    # The fresh player is fully driven by the shared last-season rate;
    # the established player has moved on from it toward their own
    # (much lower) current-season output, so should score noticeably less.
    assert fresh_xp > established_xp


def test_minutes_multiplier_scales_smoothly_not_binary(monkeypatch):
    # Bug fixed here (found via a real side-by-side comparison): a player
    # with just 152 current-season minutes was getting the exact same 1.0
    # multiplier as a 2953-minute stalwart. A small-but-nonzero minutes
    # total should land clearly below full confidence, not jump straight
    # to it the instant minutes > 0.
    barely_played = make_player(1, team=1, minutes=152, status="a")
    established = make_player(2, team=1, minutes=2953, status="a")

    barely_played_mult = xp_calculator._minutes_multiplier(barely_played)
    established_mult = xp_calculator._minutes_multiplier(established)

    assert barely_played_mult < established_mult
    assert established_mult == pytest.approx(1.0)
    assert 0.3 < barely_played_mult < 0.6  # discounted, not full confidence, not the old 0.3 floor either


def test_bonus_points_separate_elite_from_squad_depth(monkeypatch):
    # The actual calibration bug, reproduced directly: without bonus
    # points, an elite player and a squad-depth player with similar
    # underlying rates landed within ~2 points of each other over 4
    # gameweeks (confirmed via a real dry run) — appearance points and
    # clean-sheet floor dominated the total. A real bonus-rate gap
    # should now create meaningfully more separation than that.
    team = make_team(1)
    opp = make_team(2)
    elite = make_player(1, team=1, form=0.0, xgi=0.0, minutes=0, chance=100, status="a")
    squad_depth = make_player(2, team=1, form=0.0, xgi=0.0, minutes=0, chance=100, status="a")
    fixture = Fixture(id=1, event=1, team_h=1, team_a=2, team_h_difficulty=3,
                       team_a_difficulty=3, kickoff_time=None, finished=False)

    monkeypatch.setattr(xp_calculator.fpl_client, "get_players", lambda: [elite, squad_depth])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_teams", lambda: [team, opp])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_all_fixtures", lambda: [fixture])
    monkeypatch.setattr(xp_calculator.fpl_client, "get_next_gameweek", _next_gw)
    # Same underlying-output rate for both, but the elite player has a
    # real last-season bonus rate (like Haaland's actual ~1.3/90) and the
    # squad-depth player has none — this is the exact gap the model was
    # missing before bonus points were added.
    monkeypatch.setattr(
        xp_calculator.fpl_client,
        "get_last_season_rates",
        lambda: {
            1: {"egi_per_90": 0.86, "bonus_per_90": 1.3},
            2: {"egi_per_90": 0.86, "bonus_per_90": 0.0},
        },
    )

    df = xp_calculator.build_xp_table(horizon_gameweeks=1)
    elite_xp = df[df["player_id"] == 1].iloc[0]["current_gameweek_xP"]
    squad_depth_xp = df[df["player_id"] == 2].iloc[0]["current_gameweek_xP"]

    assert elite_xp > squad_depth_xp
    assert (elite_xp - squad_depth_xp) > 0.5  # meaningful separation, not a rounding-level gap
