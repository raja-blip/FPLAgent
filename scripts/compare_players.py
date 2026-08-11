"""
One-off diagnostic: show the COMPLETE calculation breakdown for two
named players, side by side, term by term — not just the final number.

Built because single-metric diagnostics (inspect_xp_blend.py,
inspect_top_players.py) each looked fine in isolation, yet the full
pipeline still produces squads that don't make sense (established
stars scoring below fringe players, budget going unspent). This shows
every intermediate value so we can see exactly where two players'
scores diverge, instead of inferring it indirectly again.

Usage:
    python scripts/compare_players.py Haaland Dowman
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402

import fpl_client  # noqa: E402
import xp_calculator  # noqa: E402
from network_utils import with_retry  # noqa: E402


def inspect(name: str, players, teams, all_fixtures, next_gw, last_season_rates):
    query = name.lower()
    matches = [p for p in players if query in p.web_name.lower()]
    if not matches:
        print(f"\n=== {name}: NOT FOUND ===")
        return
    player = matches[0]

    print(f"\n{'=' * 60}")
    print(f"{player.web_name} (id={player.id}, team={teams[player.team].name})")
    print(f"{'=' * 60}")
    print(f"  price: £{player.price}m")
    print(f"  status: {player.status}")
    print(f"  chance_of_playing_next_round: {player.chance_of_playing_next_round}")
    print(f"  current-season minutes: {player.minutes}")
    print(f"  current-season form: {player.form}")
    print(f"  current-season expected_goal_involvements_per_90: {player.expected_goal_involvements_per_90}")

    minutes_mult = xp_calculator._minutes_multiplier(player)
    print(f"\n  --- minutes_multiplier: {minutes_mult} ---")

    last_season_rate = last_season_rates.get(player.id, 0.0)
    print(f"  last_season_rate (post-shrinkage): {last_season_rate:.4f}")

    current_weight = min(player.minutes / xp_calculator.MINUTES_PHASE_IN, 1.0)
    print(f"  current_weight: {current_weight:.4f}")

    underlying_rate = (
        current_weight * player.expected_goal_involvements_per_90
        + (1 - current_weight) * last_season_rate
    )
    print(f"  blended underlying_rate: {underlying_rate:.4f}")

    # Find this player's fixtures in the target window and show the
    # actual per-fixture breakdown for the FIRST one.
    past_fixtures = [f for f in all_fixtures if f.finished]
    target_gw_ids = list(range(next_gw.id, next_gw.id + 4))
    player_fixtures = [
        f for f in all_fixtures
        if f.event in target_gw_ids and (f.team_h == player.team or f.team_a == player.team)
    ]
    print(f"\n  fixtures in window: {len(player_fixtures)}")

    total_xp = 0.0
    for f in player_fixtures:
        xp = xp_calculator.project_gameweek_points(player, f, teams, past_fixtures, last_season_rate)
        is_home = f.team_h == player.team
        opp_id = f.team_a if is_home else f.team_h
        print(f"    GW{f.event} vs {teams[opp_id].name} ({'H' if is_home else 'A'}): {xp:.2f} pts")
        total_xp += xp

    print(f"\n  TOTAL rolling_4gw_xP: {total_xp:.2f}")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/compare_players.py <name1> <name2>")
        sys.exit(1)

    print("Loading live data...")
    players = fpl_client.get_players()
    teams = {t.id: t for t in fpl_client.get_teams()}
    all_fixtures = fpl_client.get_all_fixtures()
    next_gw = fpl_client.get_next_gameweek()
    last_season_rates = fpl_client.get_last_season_output_rates()

    for name in sys.argv[1:3]:
        inspect(name, players, teams, all_fixtures, next_gw, last_season_rates)


if __name__ == "__main__":
    main()
