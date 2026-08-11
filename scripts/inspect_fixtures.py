"""
One-off diagnostic: for every team, show how many fixtures fall inside
the next-4-gameweeks window build_xp_table() actually uses.

Testing the hypothesis for why Haaland (and others) keep computing a
strong individual rate but a near-zero rolling_4gw_xP: if a team's
fixtures aren't correctly linked to the target gameweek IDs, every
player on that team gets nothing to project onto, regardless of quality.

Usage:
    python scripts/inspect_fixtures.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fpl_client  # noqa: E402


def main() -> None:
    teams = {t.id: t for t in fpl_client.get_teams()}
    all_fixtures = fpl_client.get_all_fixtures()
    next_gw = fpl_client.get_next_gameweek()

    if next_gw is None:
        print("No next gameweek found at all — that itself would explain a lot.")
        sys.exit(1)

    print(f"Next gameweek: id={next_gw.id}, name={next_gw.name}, is_next={next_gw.is_next}")

    horizon = 4
    target_gw_ids = list(range(next_gw.id, next_gw.id + horizon))
    print(f"Target gameweek IDs (matches build_xp_table exactly): {target_gw_ids}")

    print(f"\nTotal fixtures in the full dataset: {len(all_fixtures)}")
    events_present = sorted({f.event for f in all_fixtures if f.event is not None})
    print(f"Distinct 'event' (gameweek) values seen across ALL fixtures: {events_present[:20]}"
          f"{' ...' if len(events_present) > 20 else ''}")
    none_event_count = sum(1 for f in all_fixtures if f.event is None)
    print(f"Fixtures with event=None (unscheduled): {none_event_count}")

    fixtures_by_team_and_gw: dict[tuple[int, int], int] = defaultdict(int)
    for f in all_fixtures:
        if f.event in target_gw_ids:
            fixtures_by_team_and_gw[(f.team_h, f.event)] += 1
            fixtures_by_team_and_gw[(f.team_a, f.event)] += 1

    print(f"\n{'Team':20} {'Fixtures in next 4 GWs':>24}")
    print("-" * 45)
    zero_fixture_teams = []
    for team_id, team in sorted(teams.items(), key=lambda x: x[1].name):
        count = sum(fixtures_by_team_and_gw.get((team_id, gw), 0) for gw in target_gw_ids)
        print(f"{team.name:20} {count:>24}")
        if count == 0:
            zero_fixture_teams.append(team.name)

    print("\n" + "=" * 45)
    if zero_fixture_teams:
        print(f"TEAMS WITH ZERO FIXTURES IN WINDOW: {zero_fixture_teams}")
    else:
        print("Every team has at least one fixture in the window — this hypothesis is WRONG, bug is elsewhere.")


if __name__ == "__main__":
    main()
