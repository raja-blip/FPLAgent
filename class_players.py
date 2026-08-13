"""
Manual "form is temporary, class is permanent" player floor list.

Raj's principle: some players' TRUE quality is more reliable than
short-term form fluctuations capture — real evidence for this from the
champions research (2024/25 world champion Lovro Budišin held Phil
Foden through a rough patch and was rewarded with 42 points across
Gameweeks 20-22 once it turned, rather than panic-selling). Rather than
let the model's short-term signal drag a genuinely top-class player's
projection too low during a slump, these players get a FLOOR on their
projected points per fixture — never treated as worse than this
baseline, even if current stats alone would suggest so.

This does NOT force them into the squad or captaincy — the optimizer
can still leave one out if a cheaper/better-value option exists within
budget. The floor also never applies when a player genuinely isn't
playing at all (injured/suspended) — see xp_calculator.py's
project_gameweek_points, where the floor is applied after the
early-return-on-zero-minutes check, not before.

Keyed by FPL web_name (not full name) — this must match exactly what
the live API / historical dataset uses for that player, or the floor
silently won't apply. build_xp_table() prints a one-time warning for
any name in this list that doesn't match a real player that gameweek,
specifically so a typo or a transfer away from the club doesn't fail
silently.

DEFAULT_FLOOR is a starting value, not a tuned one — Raj specified the
MECHANISM (a floor) but not a specific number. 5.0 points/fixture is a
"solid week" baseline (comfortably above just appearance + a clean
sheet, well below a genuine standout game) — worth backtesting and
tuning the same way hit_margin and max_player_price were, rather than
trusted blindly.

All names verified against the real dataset before use (see
players.csv) — including confirming Semenyo is genuinely listed under
Manchester City this season (moved there in Jan '26), not Bournemouth
as an earlier stale assumption incorrectly suggested.

DECISION (post-backtest): tested and left OFF. Alone, the floor gave
+12 points — but combined with optimizer.py's max_player_price cap,
every floor value tested (2 through 6) scored WORSE than no floor at
all (2202-2143 vs. 2215 with the cap and no floor). The mechanism
fights the cap's own diversification rather than complementing it.
Raj's call: rely on his own GW1 manual pick plus the fully statistical
algorithm from GW2 onward, rather than this override. The list and
mechanism stay here, tested and working, in case this is revisited —
CLASS_PLAYERS is just empty for now.
"""

DEFAULT_FLOOR = 5.0  # points per fixture — untested value; see decision above

# Disabled — see DECISION above. Original list, kept for reference:
# CLASS_PLAYERS: dict[str, float] = {
#     "Saka": DEFAULT_FLOOR, "Gabriel": DEFAULT_FLOOR, "Gyökeres": DEFAULT_FLOOR,
#     "Cherki": DEFAULT_FLOOR, "Semenyo": DEFAULT_FLOOR,
#     "B.Fernandes": DEFAULT_FLOOR, "Mbeumo": DEFAULT_FLOOR,
#     "Szoboszlai": DEFAULT_FLOOR, "Watkins": DEFAULT_FLOOR, "Thiago": DEFAULT_FLOOR,
# }
CLASS_PLAYERS: dict[str, float] = {}
