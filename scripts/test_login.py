"""
One-off connectivity test: confirms login works, your private squad can
be read, and the Telegram bot can message you — all in one run, with
nothing about your account ever printed to the logs.

This is deliberately NOT part of the main agent flow. It's a throwaway
diagnostic for setting things up, meant to be run manually from the
Actions tab while you're wiring up secrets, not on a schedule.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fpl_actions  # noqa: E402
import fpl_auth  # noqa: E402
import telegram_notifier  # noqa: E402


def main() -> None:
    print("Logging in...")
    try:
        session = fpl_auth.login()
        print("Login succeeded — session cookie obtained.")
    except fpl_auth.FPLAuthError as exc:
        print(f"Login FAILED: {exc}")
        sys.exit(1)

    team_id = fpl_auth.get_team_id()

    print("Reading current squad...")
    try:
        squad = fpl_actions.get_current_squad(session, team_id)
        picks = squad.get("picks", [])
        bank = squad.get("transfers", {}).get("bank")
        print(f"Squad read OK — {len(picks)} picks found. Bank: {bank}")
    except Exception as exc:
        print(f"Squad read FAILED: {exc}")
        sys.exit(1)

    print("Sending Telegram test message...")
    try:
        telegram_notifier.send_message(
            "Arteta's Bulbs connection test: login, squad read, and this "
            "Telegram message all worked. Ready for the real thing."
        )
        print("Telegram message sent OK — check your phone.")
    except Exception as exc:
        print(f"Telegram send FAILED: {exc}")
        sys.exit(1)

    print("\nAll three checks passed.")


if __name__ == "__main__":
    main()
