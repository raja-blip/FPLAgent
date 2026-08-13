"""
T-3h execute-or-stand-down script.

Runs periodically (every hour or so — see .github/workflows/). Checks
whether you touched your squad yourself since the T-24h proposal; if
so, stands down entirely for this gameweek (your judgment overrides
the bot's, no questions asked). If your squad is untouched, submits
exactly what was proposed.

Wildcard and Free Hit need one extra condition beyond "squad
unchanged": an explicit "yes" reply on Telegram sent after the
proposal, since neither can be undone once played — see
propose.py and telegram_notifier.check_for_yes_confirmation.

Bench Boost and Triple Captain were already submitted (lineup + chip)
at T-24h in propose.py, since both are reversible before the deadline
— nothing further to submit here for those two, this just marks the
record executed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import agent_state  # noqa: E402
import deadline_windows  # noqa: E402
import fpl_actions  # noqa: E402
import fpl_auth  # noqa: E402
import fpl_client  # noqa: E402
import telegram_notifier  # noqa: E402

CHIP_API_CODES = {
    "wildcard": "wildcard",
    "free_hit": "freehit",
    "bench_boost": "bboost",
    "triple_captain": "3xc",
}


def main() -> None:
    next_gw = fpl_client.get_next_gameweek()
    if next_gw is None:
        print("No upcoming gameweek — season may be over. Nothing to do.")
        return

    now = time.time()
    if not deadline_windows.in_execute_window(next_gw.deadline_time_epoch, now):
        hrs = deadline_windows.hours_until(next_gw.deadline_time_epoch, now)
        print(f"Not in execute window for GW{next_gw.id} (deadline in {hrs:.1f}h). Nothing to do.")
        return

    state = agent_state.load_state()
    record = agent_state.get_gameweek_record(state, next_gw.id)

    if record is None:
        print(f"No proposal found for GW{next_gw.id} — nothing to execute. "
              f"(propose.py may have missed its window, or this is the very first gameweek.)")
        return

    if record["executed"]:
        print(f"GW{next_gw.id} already executed. Nothing to do.")
        return

    session = fpl_auth.login()
    team_id = fpl_auth.get_team_id()
    current_squad_data = fpl_actions.get_current_squad(session, team_id)
    live_squad_ids = sorted(p["element"] for p in current_squad_data["picks"])
    squad_before = sorted(record["squad_before"])

    if live_squad_ids != squad_before:
        print(
            f"Squad changed since the T-24h proposal (you made your own moves) — "
            f"standing down for GW{next_gw.id}, per the agreed design."
        )
        telegram_notifier.send_message(
            f"GW{next_gw.id}: noticed you changed your squad yourself — standing down, "
            f"your changes stand as-is."
        )
        record["executed"] = True  # standing down IS the resolution for this gameweek
        record["stood_down"] = True
        agent_state.set_gameweek_record(state, next_gw.id, record)
        agent_state.save_state(state)
        return

    chip = record["chip"]
    if record["chip_needs_confirmation"]:
        confirmed = telegram_notifier.check_for_yes_confirmation(since_timestamp=record["proposed_at"])
        if not confirmed:
            print(f"No 'yes' reply received for {chip} — skipping the chip this week, per the agreed design.")
            telegram_notifier.send_message(
                f"GW{next_gw.id}: no confirmation received for {chip.replace('_', ' ').title()} "
                f"— skipping the chip. Regular squad management continues as normal next gameweek."
            )
            record["executed"] = True
            record["chip_skipped_no_confirmation"] = True
            agent_state.set_gameweek_record(state, next_gw.id, record)
            agent_state.save_state(state)
            return

    if chip in ("bench_boost", "triple_captain"):
        # Already submitted (lineup + chip) at T-24h in propose.py —
        # nothing further to do here, just close out the record.
        print(f"{chip} was already played at proposal time. Marking executed.")
    else:
        if record["transfers_in"]:
            print(f"Submitting {len(record['transfers_in'])} transfer(s)...")
            fpl_actions.submit_transfers(
                session, team_id,
                transfers_out=record["transfers_out"],
                transfers_in=record["transfers_in"],
                current_gameweek=next_gw.id,
            )

        chip_code = CHIP_API_CODES.get(chip) if chip else None
        print(f"Submitting lineup{' with chip ' + chip if chip else ''}...")
        fpl_actions.submit_lineup(
            session, team_id,
            starting_ids=record["starting_ids"],
            bench_ids=record["bench_ids"],
            captain_id=record["captain_id"],
            vice_captain_id=record["vice_captain_id"],
            chip=chip_code,
        )

    if record["hits_taken"]:
        state["season_hits_used"] += record["hits_taken"]
        print(f"Season hit budget used: {state['season_hits_used']}")

    telegram_notifier.send_message(f"GW{next_gw.id}: plan executed successfully.")
    record["executed"] = True
    agent_state.set_gameweek_record(state, next_gw.id, record)
    agent_state.save_state(state)
    print("State saved.")


if __name__ == "__main__":
    main()
