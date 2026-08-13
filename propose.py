"""
T-24h propose script.

Runs periodically (every couple hours, see .github/workflows/ — not
at an exact instant, since FPL deadlines shift week to week). Self
checks the time window and whether this gameweek's already been
proposed, so running it more often than strictly needed is harmless —
it just no-ops.

What this does NOT do: submit transfers or lineup changes (except for
Bench Boost/Triple Captain, see below). Those wait for execute.py at
T-3h, per the agreed design — Telegram here is a proposal + FYI, the
real "did you want something different" signal is your live FPL squad
state, checked at T-3h.

Bench Boost and Triple Captain are different: both can be cancelled
any time before the deadline (verified against real FPL rules), so
per the agreed design, the chip is played NOW, immediately — you can
undo it yourself in the FPL app if you disagree, same safety net as
an ordinary transfer.

Wildcard and Free Hit are different again: NEITHER can be undone once
played. So per the agreed design, this script only PROPOSES them and
asks for an explicit "yes" reply — execute.py checks for that reply at
T-3h before ever submitting either.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import agent_state  # noqa: E402
import chip_strategy  # noqa: E402
import deadline_windows  # noqa: E402
import fpl_actions  # noqa: E402
import fpl_auth  # noqa: E402
import fpl_client  # noqa: E402
import optimizer  # noqa: E402
import telegram_notifier  # noqa: E402
import xp_calculator  # noqa: E402

HIT_MARGIN = 8.0
MAX_PLAYER_PRICE = 12.0
SEASON_HIT_BUDGET = 10

CHIP_API_CODES = {
    "wildcard": "wildcard",
    "free_hit": "freehit",
    "bench_boost": "bboost",
    "triple_captain": "3xc",
}


def _build_chip_plan_if_needed(state: dict, current_gw: int) -> dict:
    if state["chip_plan"] is not None:
        return state["chip_plan"]

    all_fixtures = fpl_client.get_all_fixtures()
    fixtures_by_gw: dict[int, list] = defaultdict(list)
    for f in all_fixtures:
        fixtures_by_gw[f.event].append(f)

    plan = chip_strategy.build_chip_plan(dict(fixtures_by_gw), current_gw=current_gw)
    state["chip_plan"] = {
        "wildcard_gw": plan.wildcard_gw,
        "bench_boost_gw": plan.bench_boost_gw,
        "triple_captain_gw": plan.triple_captain_gw,
        "free_hit_gw": plan.free_hit_gw,
    }
    print(f"Built season chip plan: {state['chip_plan']}")
    return state["chip_plan"]


def _chip_for_gameweek(chip_plan: dict, gw_id: int) -> str | None:
    for chip_name, key in [
        ("wildcard", "wildcard_gw"), ("bench_boost", "bench_boost_gw"),
        ("triple_captain", "triple_captain_gw"), ("free_hit", "free_hit_gw"),
    ]:
        if chip_plan.get(key) == gw_id:
            return chip_name
    return None


def main() -> None:
    next_gw = fpl_client.get_next_gameweek()
    if next_gw is None:
        print("No upcoming gameweek — season may be over. Nothing to do.")
        return

    now = time.time()
    if not deadline_windows.in_propose_window(next_gw.deadline_time_epoch, now):
        hrs = deadline_windows.hours_until(next_gw.deadline_time_epoch, now)
        print(f"Not in propose window for GW{next_gw.id} (deadline in {hrs:.1f}h). Nothing to do.")
        return

    state = agent_state.load_state()
    if agent_state.get_gameweek_record(state, next_gw.id) is not None:
        print(f"Already proposed for GW{next_gw.id}. Nothing to do.")
        return

    print(f"Proposing for GW{next_gw.id}...")
    chip_plan = _build_chip_plan_if_needed(state, next_gw.id)
    chip_this_week = _chip_for_gameweek(chip_plan, next_gw.id)

    session = fpl_auth.login()
    team_id = fpl_auth.get_team_id()
    current_squad_data = fpl_actions.get_current_squad(session, team_id)
    current_squad_ids = [p["element"] for p in current_squad_data["picks"]]
    free_transfers = current_squad_data.get("transfers", {}).get("limit") or 1

    xp_df = xp_calculator.build_xp_table(horizon_gameweeks=4)
    hits_remaining = max(0, SEASON_HIT_BUDGET - state["season_hits_used"])

    if chip_this_week == "wildcard":
        squad_result = optimizer.select_squad(
            xp_df, budget=100.0, existing_squad_ids=current_squad_ids,
            free_transfers=15, max_player_price=MAX_PLAYER_PRICE,
        )
    elif chip_this_week == "free_hit":
        squad_result = optimizer.select_squad(
            xp_df, budget=100.0, existing_squad_ids=None, max_player_price=MAX_PLAYER_PRICE,
        )
    else:
        squad_result = optimizer.select_squad(
            xp_df, budget=100.0, existing_squad_ids=current_squad_ids,
            free_transfers=free_transfers, hit_margin=HIT_MARGIN,
            max_player_price=MAX_PLAYER_PRICE, max_hits_remaining=hits_remaining,
        )

    lineup = optimizer.select_starting_xi(squad_result.squad_ids, xp_df)

    by_id = {row["player_id"]: row for row in xp_df.to_dict("records")}

    def name(pid: int) -> str:
        return by_id.get(pid, {}).get("web_name", f"#{pid}")

    chip_already_submitted = False
    if chip_this_week in ("bench_boost", "triple_captain"):
        print(f"Playing {chip_this_week} now (reversible before deadline)...")
        fpl_actions.submit_lineup(
            session, team_id, starting_ids=lineup.starting_ids, bench_ids=lineup.bench_ids,
            captain_id=lineup.captain_id, vice_captain_id=lineup.vice_captain_id,
            chip=CHIP_API_CODES[chip_this_week],
        )
        chip_already_submitted = True

    lines = [f"*Gameweek {next_gw.id} plan*"]
    if chip_this_week:
        lines.append(f"Chip: *{chip_this_week.replace('_', ' ').title()}*")
    if squad_result.transfers_in:
        for out_id, in_id in zip(squad_result.transfers_out, squad_result.transfers_in):
            lines.append(f"Transfer: {name(out_id)} -> {name(in_id)}")
        if squad_result.hits_taken:
            lines.append(f"({squad_result.hits_taken} hit(s), -{squad_result.hits_taken * 4} pts)")
    else:
        lines.append("No transfers.")
    lines.append(f"Captain: {name(lineup.captain_id)} (VC: {name(lineup.vice_captain_id)})")
    lines.append("")

    if chip_this_week in ("wildcard", "free_hit"):
        lines.append(
            f"This chip *cannot be undone* once played. Reply *YES* to confirm, "
            f"or do nothing to skip it this week."
        )
    elif chip_this_week in ("bench_boost", "triple_captain"):
        lines.append("Chip played now — you can undo it yourself in the FPL app if you disagree.")
    else:
        lines.append(
            "This goes through automatically in ~21 hours unless you change your "
            "squad yourself in the FPL app before then."
        )

    telegram_notifier.send_message("\n".join(lines))
    print("Telegram message sent.")

    agent_state.set_gameweek_record(state, next_gw.id, {
        "proposed_at": now,
        "squad_before": current_squad_ids,
        "transfers_in": squad_result.transfers_in,
        "transfers_out": squad_result.transfers_out,
        "proposed_squad": squad_result.squad_ids,
        "starting_ids": lineup.starting_ids,
        "bench_ids": lineup.bench_ids,
        "captain_id": lineup.captain_id,
        "vice_captain_id": lineup.vice_captain_id,
        "hits_taken": squad_result.hits_taken,
        "chip": chip_this_week,
        "chip_needs_confirmation": chip_this_week in ("wildcard", "free_hit"),
        "chip_already_submitted": chip_already_submitted,
        "executed": chip_already_submitted,
    })
    agent_state.save_state(state)
    print("State saved.")


if __name__ == "__main__":
    main()
