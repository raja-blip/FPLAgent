"""
Expected Points (xP) calculator.

Estimates each player's expected FPL points for the next gameweek and over
a rolling 4-gameweek horizon, using:
  - underlying output rate (expected_goal_involvements blended with FPL's
    own 'form' field, which is already a recent-points rolling average)
  - position-specific FPL scoring rules
  - opponent strength (attack/defence, home/away specific) rather than
    raw FDR, per the design we agreed on
  - a small head-to-head nudge from this-season meetings between the two
    teams, when any have already been played
  - a minutes/rotation-risk multiplier from chance_of_playing_next_round
    and recent minutes played, discounting rather than excluding, per our
    "moderate" rotation-risk rule

Known simplification (flagged, not hidden): head-to-head only looks at
*this season's* meetings via the fixtures endpoint. Early in the season
most team pairs haven't met yet, so this factor will mostly sit neutral
until enough of the season has been played. Deeper multi-season
head-to-head would need an external historical data source (e.g.
football-data.co.uk) — worth adding later if this factor doesn't carry
enough signal on its own once we can evaluate it against real results.

Known simplification: double/blank gameweeks (a team playing twice, or
not at all, in one event due to cup scheduling or postponements) aren't
specially handled yet — rolling_4gw_xP just sums whatever fixtures fall
in the next 4 gameweek IDs for a player's team, however many that is.
Fine for most of the season; worth revisiting around cup-heavy weeks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

import fpl_client
from models import Fixture, Team, Player

# Position-specific FPL scoring (2026/27 rules)
GOAL_POINTS = {1: 10, 2: 6, 3: 5, 4: 4}  # GK, DEF, MID, FWD
ASSIST_POINTS = 3
CLEAN_SHEET_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}
APPEARANCE_POINTS_60_MIN = 2
APPEARANCE_POINTS_UNDER_60 = 1

LEAGUE_AVG_STRENGTH = 1200  # rough FPL team-strength midpoint, used to normalize
H2H_NUDGE_WEIGHT = 0.08  # deliberately small — a nudge, not a driver


@dataclass
class GameweekProjection:
    gameweek_id: int
    is_home: bool
    opponent_team_id: int
    xp: float


def _minutes_multiplier(player: Player) -> float:
    """Rough probability-of-meaningful-minutes factor.

    Per our agreed "moderate" rotation-risk rule: only clearly-doubtful
    players get excluded (upstream, in the optimizer) — here we just
    discount xP smoothly, so a 75%-fit player shows up as a slightly
    reduced option rather than disappearing from the pool entirely.
    """
    if player.status in ("i", "s", "u"):
        return 0.0
    if player.chance_of_playing_next_round is not None:
        return player.chance_of_playing_next_round / 100
    if player.minutes == 0:
        return 0.3  # unproven this season — steep discount, not zero
    return 1.0


def _opponent_strength_factor(team: Team, opponent: Team, is_home: bool) -> tuple[float, float]:
    """Attack and defence adjustment factors relative to league average.

    Returns (attack_boost, defence_boost): attack_boost scales the
    player's own attacking output based on how weak/strong the opponent's
    defence is; defence_boost scales clean-sheet likelihood based on how
    weak/strong the opponent's attack is.

    Falls back to a neutral (1.0) boost when strength data is missing —
    early in a season, some teams' strength ratings come back null from
    the live API rather than a real number.
    """
    if is_home:
        opp_defence = opponent.strength_defence_away
        opp_attack = opponent.strength_attack_away
    else:
        opp_defence = opponent.strength_defence_home
        opp_attack = opponent.strength_attack_home

    attack_boost = LEAGUE_AVG_STRENGTH / opp_defence if opp_defence else 1.0
    defence_boost = LEAGUE_AVG_STRENGTH / opp_attack if opp_attack else 1.0
    return attack_boost, defence_boost


def _head_to_head_nudge(team_id: int, opponent_id: int, past_fixtures: list[Fixture]) -> float:
    """Small secondary nudge from this-season meetings only (see module docstring)."""
    relevant = [
        f
        for f in past_fixtures
        if f.finished and {f.team_h, f.team_a} == {team_id, opponent_id}
    ]
    return 1.0 + H2H_NUDGE_WEIGHT if relevant else 1.0


def _score_output(player: Player, attack_boost: float) -> tuple[float, float]:
    """Expected goals and assists for this fixture, from blended output rate."""
    underlying_rate = player.expected_goal_involvements
    recent_signal = player.form / 5  # normalize FPL's 0-10ish form scale
    blended = (0.6 * underlying_rate) + (0.4 * recent_signal)

    goal_share = 0.55  # typical split of goal involvements that are goals vs assists
    xg = blended * goal_share * attack_boost
    xa = blended * (1 - goal_share) * attack_boost
    return xg, xa


def _clean_sheet_probability(defence_boost: float) -> float:
    base_rate = 0.30  # rough league-average clean-sheet rate
    return min(base_rate * defence_boost, 0.75)


def project_gameweek_points(
    player: Player,
    fixture: Fixture,
    teams_by_id: dict[int, Team],
    past_fixtures: list[Fixture],
) -> float:
    """Expected points for one player in one fixture."""
    is_home = fixture.team_h == player.team
    opponent_id = fixture.team_a if is_home else fixture.team_h
    team = teams_by_id[player.team]
    opponent = teams_by_id[opponent_id]

    minutes_mult = _minutes_multiplier(player)
    if minutes_mult == 0:
        return 0.0

    attack_boost, defence_boost = _opponent_strength_factor(team, opponent, is_home)
    h2h_nudge = _head_to_head_nudge(player.team, opponent_id, past_fixtures)

    xg, xa = _score_output(player, attack_boost * h2h_nudge)
    goal_pts = xg * GOAL_POINTS.get(player.element_type, 4)
    assist_pts = xa * ASSIST_POINTS

    cs_prob = _clean_sheet_probability(defence_boost)
    cs_pts = cs_prob * CLEAN_SHEET_POINTS.get(player.element_type, 0)

    appearance_pts = APPEARANCE_POINTS_60_MIN if minutes_mult > 0.6 else APPEARANCE_POINTS_UNDER_60

    total = (goal_pts + assist_pts + cs_pts + appearance_pts) * minutes_mult
    return round(total, 2)


def build_xp_table(horizon_gameweeks: int = 4) -> pd.DataFrame:
    """Main entry point: one row per player, current-GW and rolling xP."""
    players = fpl_client.get_players()
    teams = {t.id: t for t in fpl_client.get_teams()}
    all_fixtures = fpl_client.get_all_fixtures()
    next_gw = fpl_client.get_next_gameweek()

    if next_gw is None:
        raise RuntimeError("No upcoming gameweek found — is the season over?")

    past_fixtures = [f for f in all_fixtures if f.finished]
    target_gw_ids = list(range(next_gw.id, next_gw.id + horizon_gameweeks))

    fixtures_by_team_and_gw: dict[tuple[int, int], list[Fixture]] = defaultdict(list)
    for f in all_fixtures:
        if f.event in target_gw_ids:
            fixtures_by_team_and_gw[(f.team_h, f.event)].append(f)
            fixtures_by_team_and_gw[(f.team_a, f.event)].append(f)

    rows = []
    for player in players:
        current_gw_xp = 0.0
        rolling_xp = 0.0
        for i, gw_id in enumerate(target_gw_ids):
            fixtures_this_gw = fixtures_by_team_and_gw.get((player.team, gw_id), [])
            gw_total = sum(
                project_gameweek_points(player, f, teams, past_fixtures)
                for f in fixtures_this_gw
            )
            if i == 0:
                current_gw_xp = gw_total
            rolling_xp += gw_total

        rows.append(
            {
                "player_id": player.id,
                "web_name": player.web_name,
                "position": player.element_type,
                "team": player.team,
                "price": player.price,
                "current_gameweek_xP": round(current_gw_xp, 2),
                "rolling_4gw_xP": round(rolling_xp, 2),
            }
        )

    return pd.DataFrame(rows)
