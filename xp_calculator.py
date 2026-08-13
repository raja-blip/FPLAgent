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
  - an expected-bonus-points estimate, blended the same way as the
    underlying output rate (last season's per-90 bonus rate, phased
    toward this season's own data as real minutes accumulate)

Bonus points were added after a real calibration check found the model
without them couldn't separate elite players from squad depth at all —
everyone landed within about 2 points of each other over 4 gameweeks,
because appearance points and clean-sheet floor dominated the total and
the goals/assists component wasn't enough on its own. Real FPL
disproportionately rewards standout individual performances via bonus
points (up to 3 extra for a match's best performers) — modeling that
using each player's own actual last-season bonus rate (not a guessed
formula weight) is what actually fixes the separation.

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
from class_players import CLASS_PLAYERS
from models import Fixture, Team, Player
from team_overrides import TEAM_OVERRIDES

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


MINUTES_CONFIDENCE_FULL = 900  # ~10 full matches — full confidence beyond this


def _minutes_multiplier(player: Player) -> float:
    """Rough probability-of-meaningful-minutes factor.

    Bug fixed here (found via a real side-by-side comparison: a player
    with 152 current-season minutes was getting the exact same 1.0
    confidence as a stalwart with 2953): this used to jump straight from
    a 0.3 floor (0 minutes) to full 1.0 confidence the instant a player
    had ANY nonzero minutes, no matter how few. Now it scales smoothly
    with actual minutes played, so someone with a handful of minutes
    lands closer to the uncertain end, not treated as equally nailed-on
    as an established starter.
    """
    if player.status in ("i", "s", "u"):
        return 0.0
    if player.chance_of_playing_next_round is not None:
        return player.chance_of_playing_next_round / 100
    if player.minutes == 0:
        return 0.3  # unproven this season — steep discount, not zero
    return 0.3 + 0.7 * min(player.minutes / MINUTES_CONFIDENCE_FULL, 1.0)


def _opponent_strength_factor(team: Team, opponent: Team, is_home: bool) -> tuple[float, float]:
    """Attack and defence adjustment factors relative to league average.

    Returns (attack_boost, defence_boost): attack_boost scales the
    player's own attacking output based on how weak/strong the opponent's
    defence is; defence_boost scales clean-sheet likelihood based on how
    weak/strong the opponent's attack is.

    Falls back to a neutral (1.0) boost when strength data is missing —
    early in a season, some teams' strength ratings come back null from
    the live API rather than a real number.

    Applies TEAM_OVERRIDES on top of whatever FPL data exists (or the
    neutral fallback) — see team_overrides.py for what these represent
    and how to edit them.
    """
    if is_home:
        opp_defence = opponent.strength_defence_away
        opp_attack = opponent.strength_attack_away
    else:
        opp_defence = opponent.strength_defence_home
        opp_attack = opponent.strength_attack_home

    override = TEAM_OVERRIDES.get(opponent.name, {})
    defence_multiplier = override.get("defence", 1.0)  # <1.0 = weaker defence than rated
    attack_multiplier = override.get("attack", 1.0)  # <1.0 = weaker attack than rated

    effective_defence = (opp_defence * defence_multiplier) if opp_defence else None
    effective_attack = (opp_attack * attack_multiplier) if opp_attack else None

    attack_boost = (
        LEAGUE_AVG_STRENGTH / effective_defence if effective_defence else 1.0 / defence_multiplier
    )
    defence_boost = (
        LEAGUE_AVG_STRENGTH / effective_attack if effective_attack else 1.0 / attack_multiplier
    )
    return attack_boost, defence_boost


def _head_to_head_nudge(team_id: int, opponent_id: int, past_fixtures: list[Fixture]) -> float:
    """Small secondary nudge from this-season meetings only (see module docstring)."""
    relevant = [
        f
        for f in past_fixtures
        if f.finished and {f.team_h, f.team_a} == {team_id, opponent_id}
    ]
    return 1.0 + H2H_NUDGE_WEIGHT if relevant else 1.0


MINUTES_PHASE_IN = 270  # ~3 full matches — full current-season weight beyond this


def _score_output(
    player: Player, attack_boost: float, last_season_egi_rate: float, last_season_bonus_rate: float
) -> tuple[float, float, float]:
    """Expected goals, assists, and bonus points for this fixture.

    Bug fixed here (found via a real dry-run producing ~30 points/player/
    gameweek, an order of magnitude too high): expected_goal_involvements
    is a SEASON-CUMULATIVE total, not a per-match rate — using it directly
    as a single-fixture rate massively overstated every projection.
    expected_goal_involvements_per_90 is the field FPL provides for this.

    Second fix, same root cause: current-season data (rate, form, AND
    bonus) is meaningless before real minutes exist — pre-season, or
    early on with few minutes played. This phases from last season's
    per-90 rates to this season's own data as current-season minutes
    accumulate, rather than trusting a near-zero current-season signal.
    Underlying-output, recent-form, AND bonus all use the same phase-in
    weight, since all three are equally season-reset.

    Bonus points are NOT scaled by attack_boost (unlike goals/assists) —
    they're a broader "how good was this player's overall match" signal
    (tackles, saves, general involvement count toward BPS too, not just
    goal threat), so opponent attacking/defensive strength isn't as
    direct a driver of it as it is for goal involvements specifically.
    """
    current_weight = min(player.minutes / MINUTES_PHASE_IN, 1.0)
    underlying_rate = (
        current_weight * player.expected_goal_involvements_per_90
        + (1 - current_weight) * last_season_egi_rate
    )

    current_bonus_rate = (player.bonus / player.minutes * 90) if player.minutes > 0 else 0.0
    bonus_rate = current_weight * current_bonus_rate + (1 - current_weight) * last_season_bonus_rate

    recent_signal = player.form / 5  # normalize FPL's 0-10ish form scale
    form_weight = 0.4 * current_weight  # fades to 0 pre-season, same reasoning as above
    blended = ((1 - form_weight) * underlying_rate) + (form_weight * recent_signal)

    goal_share = 0.55  # typical split of goal involvements that are goals vs assists
    xg = blended * goal_share * attack_boost
    xa = blended * (1 - goal_share) * attack_boost
    return xg, xa, bonus_rate


def _clean_sheet_probability(defence_boost: float) -> float:
    base_rate = 0.30  # rough league-average clean-sheet rate
    return min(base_rate * defence_boost, 0.75)


def project_gameweek_points(
    player: Player,
    fixture: Fixture,
    teams_by_id: dict[int, Team],
    past_fixtures: list[Fixture],
    last_season_egi_rate: float = 0.0,
    last_season_bonus_rate: float = 0.0,
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

    xg, xa, bonus_pts = _score_output(
        player, attack_boost * h2h_nudge, last_season_egi_rate, last_season_bonus_rate
    )
    goal_pts = xg * GOAL_POINTS.get(player.element_type, 4)
    assist_pts = xa * ASSIST_POINTS

    cs_prob = _clean_sheet_probability(defence_boost)
    cs_pts = cs_prob * CLEAN_SHEET_POINTS.get(player.element_type, 0)

    appearance_pts = APPEARANCE_POINTS_60_MIN if minutes_mult > 0.6 else APPEARANCE_POINTS_UNDER_60

    total = (goal_pts + assist_pts + cs_pts + bonus_pts + appearance_pts) * minutes_mult

    # "Form is temporary, class is permanent" floor — see class_players.py.
    # Only applies here, AFTER the minutes_mult==0 early return above, so
    # a genuinely injured/suspended class player still correctly scores
    # 0, never propped up by the floor. A slump while actually playing
    # is exactly what this is meant to protect against, not unavailability.
    floor = CLASS_PLAYERS.get(player.web_name)
    if floor is not None and total < floor:
        total = floor

    return round(total, 2)


def build_xp_table(horizon_gameweeks: int = 4) -> pd.DataFrame:
    """Main entry point: one row per player, current-GW and rolling xP."""
    players = fpl_client.get_players()
    teams = {t.id: t for t in fpl_client.get_teams()}
    all_fixtures = fpl_client.get_all_fixtures()
    next_gw = fpl_client.get_next_gameweek()
    last_season_rates = fpl_client.get_last_season_rates()

    if next_gw is None:
        raise RuntimeError("No upcoming gameweek found — is the season over?")

    live_web_names = {p.web_name for p in players}
    unmatched_class_players = [name for name in CLASS_PLAYERS if name not in live_web_names]
    if unmatched_class_players:
        print(
            f"[xp_calculator] WARNING: class_players.py lists names not found among "
            f"current players — floor will NOT apply for these: {unmatched_class_players}. "
            f"Check for a typo, or a player who's since transferred/left the league."
        )

    past_fixtures = [f for f in all_fixtures if f.finished]
    target_gw_ids = list(range(next_gw.id, next_gw.id + horizon_gameweeks))

    fixtures_by_team_and_gw: dict[tuple[int, int], list[Fixture]] = defaultdict(list)
    for f in all_fixtures:
        if f.event in target_gw_ids:
            fixtures_by_team_and_gw[(f.team_h, f.event)].append(f)
            fixtures_by_team_and_gw[(f.team_a, f.event)].append(f)

    rows = []
    for player in players:
        player_rates = last_season_rates.get(player.id, {})
        last_season_egi_rate = player_rates.get("egi_per_90", 0.0)
        last_season_bonus_rate = player_rates.get("bonus_per_90", 0.0)
        current_gw_xp = 0.0
        rolling_xp = 0.0
        for i, gw_id in enumerate(target_gw_ids):
            fixtures_this_gw = fixtures_by_team_and_gw.get((player.team, gw_id), [])
            gw_total = sum(
                project_gameweek_points(
                    player, f, teams, past_fixtures, last_season_egi_rate, last_season_bonus_rate
                )
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
