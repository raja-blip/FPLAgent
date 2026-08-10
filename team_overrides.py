"""
Manual team-strength overrides.

The xP model's opponent-strength signal (FPL's own team ratings) can be
missing entirely pre-season, or slow to reflect summer changes — a new
manager, key departures, a squad gutted of experience. This file is the
one place to inject that kind of real football knowledge deliberately,
rather than it living only in your head and getting applied
inconsistently (or not at all).

How to use: add a team below with a multiplier UNDER 1.0 to say
"weaker than the stats currently suggest" for that side (attack and/or
defence, independently), or ABOVE 1.0 for "stronger than rated". Any
team not listed here gets 1.0 — no change, purely stats-driven.

Key by the exact team name as FPL lists it in bootstrap-static's
"teams" data (check there if unsure of exact spelling/capitalization).

Review and clear this out each pre-season. These are your own current
judgment calls about specific squad/manager changes — not something
that should silently persist and go stale once a team's actually
played its way back to normal.

Last reviewed: (fill in when you update this)
"""

TEAM_OVERRIDES: dict[str, dict[str, float]] = {
    # Example — Newcastle lost key defensive spine + manager this summer,
    # tipped to struggle defensively despite last season's strong numbers:
    # "Newcastle": {"defence": 0.85},
}
