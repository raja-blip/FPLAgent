"""
One-off: build the season-opening squad from live data and either show
it (dry run, default) or actually submit it to your FPL account
(--confirm).

This is NOT part of the T-24h/T-3h weekly loop — that loop is for
in-season transfer decisions, constrained by free transfers and hit
costs. Right now, before a single gameweek has been played, there's no
existing squad to "transfer" from in any meaningful sense — FPL itself
treats pre-season squad building as unlimited and free, so this runs
select_squad() as a from-scratch build (existing_squad_ids=None), not
a transfer optimization.

Usage:
    python scripts/pick_initial_squad.py               # dry run, prints only
    python scripts/pick_initial_squad.py --confirm      # actually submits
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fpl_actions  # noqa: E402
import fpl_auth  # noqa: E402
import optimizer  # noqa: E402
import xp_calculator  # noqa: E402

BUDGET = 100.0
POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "Actually submit the squad to your FPL account. Without this "
            "flag, only prints the proposed squad — nothing is submitted."
        ),
    )
    args = parser.parse_args()

    print("Building expected-points table from live data...")
    xp_df = xp_calculator.build_xp_table(horizon_gameweeks=4)

    print("Selecting best 15-man squad within budget...")
    squad_result = optimizer.select_squad(xp_df, budget=BUDGET, existing_squad_ids=None)

    print("Selecting starting XI, bench order, captain, and vice-captain...")
    lineup = optimizer.select_starting_xi(squad_result.squad_ids, xp_df)

    by_id = {row["player_id"]: row for row in xp_df.to_dict("records")}

    print("\n" + "=" * 60)
    print("PROPOSED SQUAD")
    print("=" * 60)
    total_price = sum(by_id[i]["price"] for i in squad_result.squad_ids)
    print(f"Projected points (next 4 GWs): {squad_result.projected_xp}")
    print(f"Total cost: £{total_price:.1f}m / £{BUDGET}m\n")

    print("STARTING XI:")
    for pid in lineup.starting_ids:
        p = by_id[pid]
        tag = ""
        if pid == lineup.captain_id:
            tag = "  (C)"
        elif pid == lineup.vice_captain_id:
            tag = "  (VC)"
        print(f"  {POSITION_NAMES[p['position']]:4} {p['web_name']:20} £{p['price']:.1f}m{tag}")

    print("\nBENCH (in order):")
    for pid in lineup.bench_ids:
        p = by_id[pid]
        print(f"  {POSITION_NAMES[p['position']]:4} {p['web_name']:20} £{p['price']:.1f}m")

    print("\n" + "=" * 60)

    if not args.confirm:
        print("\nDRY RUN — nothing was submitted. Re-run with --confirm to push this live.")
        return

    print("\nSubmitting to your FPL account...")
    session = fpl_auth.login()
    team_id = fpl_auth.get_team_id()
    fpl_actions.submit_lineup(
        session,
        team_id,
        starting_ids=lineup.starting_ids,
        bench_ids=lineup.bench_ids,
        captain_id=lineup.captain_id,
        vice_captain_id=lineup.vice_captain_id,
    )
    print("Squad submitted successfully.")


if __name__ == "__main__":
    main()
