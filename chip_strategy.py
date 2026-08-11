"""
Chip-usage detection and strategy: Wildcard, Free Hit, Bench Boost,
Triple Captain.

Backtest-validated (2025/26 season, +31 points from a real chip
schedule built off real double/blank gameweeks): Wildcard right before
the season's biggest double gameweek, Bench Boost ON that double,
Triple Captain on the second-biggest double, Free Hit on the biggest
blank gameweek (a common real-world pattern, since a big double is
often immediately followed by a blank as postponed fixtures get
rescheduled).

This module works against EITHER live fpl_client data or the
historical_data loader — both produce the same Fixture shape (team_h,
team_a, event), which is all detect_double_and_blank_gameweeks needs.
That's what lets the exact same chip logic run in the backtest and the
real weekly T-24h proposal script.

Known simplification, stated plainly: this is the "simplified first
version" agreed early in the project — scan the whole season in
advance for the standout double/blank gameweeks and trigger once at
the single best-identified opportunity per chip, rather than a fully
sequential "is this week good enough, or should I wait for a better
one" comparison. Each chip can genuinely only be used once (or twice,
under newer FPL rules) per season, so a more sophisticated version
would weigh opportunities against each other rather than picking each
chip's own single best week independently — worth revisiting once this
simpler version has been used for a season and its real weaknesses are
visible.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from models import Fixture


@dataclass
class ChipPlan:
    wildcard_gw: int | None
    bench_boost_gw: int | None
    triple_captain_gw: int | None
    free_hit_gw: int | None


def detect_double_and_blank_gameweeks(
    fixtures_by_gw: dict[int, list[Fixture]], total_teams: int = 20
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Given a full season's fixtures (gameweek -> that week's fixtures),
    finds genuine double gameweeks (a team playing twice) and blank
    gameweeks (a team not playing at all).

    Returns (doubles, blanks), each a list of (gameweek, team_count)
    sorted by team_count descending — doubles[0] is the gameweek where
    the most teams played twice.
    """
    doubles = []
    blanks = []
    for gw, fixtures in fixtures_by_gw.items():
        team_counts: dict[int, int] = defaultdict(int)
        for f in fixtures:
            team_counts[f.team_h] += 1
            team_counts[f.team_a] += 1
        n_doubled = sum(1 for c in team_counts.values() if c == 2)
        n_blank = total_teams - len(team_counts)
        if n_doubled > 0:
            doubles.append((gw, n_doubled))
        if n_blank > 0:
            blanks.append((gw, n_blank))

    doubles.sort(key=lambda x: -x[1])
    blanks.sort(key=lambda x: -x[1])
    return doubles, blanks


def build_chip_plan(
    fixtures_by_gw: dict[int, list[Fixture]],
    current_gw: int,
    total_teams: int = 20,
) -> ChipPlan:
    """The simplified chip schedule, built from real remaining-season
    fixtures: Wildcard the week before the biggest remaining double,
    Bench Boost on that double, Triple Captain on the second-biggest
    remaining double, Free Hit on the biggest remaining blank.

    Only considers gameweeks >= current_gw — already-past opportunities
    aren't usable. Returns None for a chip if no suitable gameweek
    remains (e.g. the season's doubles have already passed).
    """
    remaining = {gw: fx for gw, fx in fixtures_by_gw.items() if gw >= current_gw}
    doubles, blanks = detect_double_and_blank_gameweeks(remaining, total_teams)

    bench_boost_gw = doubles[0][0] if len(doubles) >= 1 else None
    triple_captain_gw = doubles[1][0] if len(doubles) >= 2 else None
    free_hit_gw = blanks[0][0] if len(blanks) >= 1 else None
    wildcard_gw = (bench_boost_gw - 1) if bench_boost_gw and bench_boost_gw > current_gw else None

    return ChipPlan(
        wildcard_gw=wildcard_gw,
        bench_boost_gw=bench_boost_gw,
        triple_captain_gw=triple_captain_gw,
        free_hit_gw=free_hit_gw,
    )
