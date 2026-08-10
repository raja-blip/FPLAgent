"""
One-off diagnostic: look up a player by name and print their raw
element-summary data, specifically history_past (prior seasons).

We need this before building the "fall back to last season's stats
pre-season" fix — the exact field names in history_past aren't
something I can verify without hitting the live endpoint, and this
project has already hit two wrong assumptions about FPL's real data
shape this week. Better to look before building on top of it again.

Usage:
    python scripts/inspect_player_history.py Haaland
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402

import fpl_client  # noqa: E402
from network_utils import with_retry  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_player_history.py <name-substring>")
        sys.exit(1)

    query = sys.argv[1].lower()
    players = fpl_client.get_players()
    matches = [p for p in players if query in p.web_name.lower()]

    if not matches:
        print(f"No player found matching '{query}'")
        sys.exit(1)

    player = matches[0]
    print(f"Found: {player.web_name} (id={player.id})")
    if len(matches) > 1:
        print(f"  (note: {len(matches)} matches, showing the first: "
              f"{[m.web_name for m in matches]})")

    url = f"https://fantasy.premierleague.com/api/element-summary/{player.id}/"
    response = with_retry(lambda: requests.get(url, timeout=15), what="element-summary")
    response.raise_for_status()
    data = response.json()

    print(f"\nTop-level keys: {list(data.keys())}")

    history_past = data.get("history_past", [])
    print(f"\nhistory_past has {len(history_past)} season(s)")

    if history_past:
        most_recent = history_past[-1]
        print("\nMost recent past season — ALL fields:")
        for key, value in most_recent.items():
            print(f"  {key}: {value}")
    else:
        print("\nNo history_past data for this player (may be new to the league).")


if __name__ == "__main__":
    main()
