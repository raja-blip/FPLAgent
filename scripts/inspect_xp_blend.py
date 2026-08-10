"""
One-off diagnostic: for a named player, print the exact numbers feeding
into the last-season-fallback blend — current-season minutes, current
per-90 rate, last-season per-90 rate, and the resulting phase-in weight.

Built specifically to find why a real, successfully-fetched last-season
rate wasn't visibly changing squad selection — rather than guess again,
this shows the actual values at the exact point they're used.

Usage:
    python scripts/inspect_xp_blend.py Haaland
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402

import fpl_client  # noqa: E402
import xp_calculator  # noqa: E402
from network_utils import with_retry  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_xp_blend.py <name-substring>")
        sys.exit(1)

    query = sys.argv[1].lower()
    players = fpl_client.get_players()
    matches = [p for p in players if query in p.web_name.lower()]

    if not matches:
        print(f"No player found matching '{query}'")
        sys.exit(1)

    player = matches[0]
    print(f"Player: {player.web_name} (id={player.id})")
    print(f"  current-season minutes: {player.minutes}")
    print(f"  current-season form: {player.form}")
    print(f"  current-season expected_goal_involvements_per_90: {player.expected_goal_involvements_per_90}")
    print(f"  status: {player.status}")
    print(f"  chance_of_playing_next_round: {player.chance_of_playing_next_round}")

    # Fetch just THIS player's last-season rate directly (not the full
    # 577-player sweep) so this stays fast.
    url = f"https://fantasy.premierleague.com/api/element-summary/{player.id}/"
    response = with_retry(lambda: requests.get(url, timeout=15), what="element-summary")
    response.raise_for_status()
    data = response.json()
    history_past = data.get("history_past", [])

    if not history_past:
        last_season_rate = 0.0
        print("  no history_past data")
    else:
        most_recent = history_past[-1]
        minutes = most_recent.get("minutes", 0) or 0
        egi = float(most_recent.get("expected_goal_involvements", 0.0) or 0.0)
        last_season_rate = (egi / minutes * 90) if minutes > 0 else 0.0
        print(f"  last season ({most_recent.get('season_name')}): "
              f"{egi} EGI over {minutes} mins -> {last_season_rate:.3f} per 90")

    current_weight = min(player.minutes / xp_calculator.MINUTES_PHASE_IN, 1.0)
    underlying_rate = (
        current_weight * player.expected_goal_involvements_per_90
        + (1 - current_weight) * last_season_rate
    )

    print(f"\n  current_weight (0=all last-season, 1=all current-season): {current_weight:.3f}")
    print(f"  resulting blended underlying_rate: {underlying_rate:.3f}")


if __name__ == "__main__":
    main()
