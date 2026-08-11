"""
One-off diagnostic: run the REAL build_xp_table() pipeline and print the
top 20 players by rolling_4gw_xP, plus a specific named player's row.

This narrows down which half of the pipeline is broken: if a strong
player's rolling_4gw_xP comes out low despite a good underlying rate
(confirmed separately via inspect_xp_blend.py), the bug is in
project_gameweek_points/_opponent_strength_factor. If it comes out
high but the optimizer still doesn't pick them, the bug is in
optimizer.py's MILP itself.

Usage:
    python scripts/inspect_top_players.py Haaland
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import xp_calculator  # noqa: E402

POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def main() -> None:
    query = sys.argv[1].lower() if len(sys.argv) > 1 else None

    print("Building the real xP table (this takes a few minutes — ~577 API calls)...")
    df = xp_calculator.build_xp_table(horizon_gameweeks=4)

    print(f"\n{'Player':20} {'Pos':4} {'Price':>7} {'GW xP':>8} {'4GW xP':>8}")
    print("-" * 55)
    top20 = df.sort_values("rolling_4gw_xP", ascending=False).head(20)
    for _, row in top20.iterrows():
        print(
            f"{row['web_name']:20} {POSITION_NAMES.get(row['position'], '?'):4} "
            f"£{row['price']:>5.1f}m {row['current_gameweek_xP']:>8.2f} {row['rolling_4gw_xP']:>8.2f}"
        )

    if query:
        matches = df[df["web_name"].str.lower().str.contains(query)]
        print(f"\n--- Rows matching '{query}' ---")
        if matches.empty:
            print("  (no match found)")
        else:
            for _, row in matches.iterrows():
                print(
                    f"{row['web_name']:20} {POSITION_NAMES.get(row['position'], '?'):4} "
                    f"£{row['price']:>5.1f}m {row['current_gameweek_xP']:>8.2f} {row['rolling_4gw_xP']:>8.2f}"
                )
                rank = (df["rolling_4gw_xP"] > row["rolling_4gw_xP"]).sum() + 1
                print(f"  -> rank {rank} of {len(df)} players by rolling_4gw_xP")


if __name__ == "__main__":
    main()
