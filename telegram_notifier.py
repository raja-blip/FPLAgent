"""
Sends messages via the Telegram bot you created in Phase 4 setup.

This covers one-way sending only — the T-24h plan summary and the T-3h
outcome notification. A full two-way conversational loop (you asking
"why not X" and getting a real answer) is a good next addition once
this simpler one-way version is proven out over a few real gameweeks.
"""
from __future__ import annotations

import os

import requests

from network_utils import with_retry

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_UPDATES_API = "https://api.telegram.org/bot{token}/getUpdates"


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    response = with_retry(
        lambda: requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        ),
        what="Telegram send_message",
    )
    response.raise_for_status()


def get_updates(since_timestamp: float | None = None) -> list[dict]:
    """Pulls recent messages sent to the bot — this is how the T-3h run
    reads whatever you replied, without needing anything to be
    listening live. Telegram just holds messages until something asks
    for them (getUpdates), the same way an email inbox holds mail
    whether or not you're looking at it right now.

    since_timestamp: if given (a Unix timestamp), only returns messages
    sent after that time — used to ignore anything sent before this
    week's T-24h proposal, so an old reply can't accidentally count
    for a different week's chip decision.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    response = with_retry(
        lambda: requests.get(
            TELEGRAM_UPDATES_API.format(token=token),
            params={"timeout": 0},
            timeout=15,
        ),
        what="Telegram get_updates",
    )
    response.raise_for_status()
    data = response.json()

    updates = data.get("result", [])
    messages = [u["message"] for u in updates if "message" in u]

    if since_timestamp is not None:
        messages = [m for m in messages if m.get("date", 0) >= since_timestamp]

    return messages


def check_for_yes_confirmation(since_timestamp: float) -> bool:
    """Checks whether you replied something starting with 'yes' (case
    insensitive) after the given timestamp — used specifically for
    Wildcard/Free Hit, where the default is DO NOTHING unless you
    explicitly confirmed (opposite of every other decision this agent
    makes, since these two chips can't be undone once played).
    """
    messages = get_updates(since_timestamp=since_timestamp)
    for msg in messages:
        text = msg.get("text", "").strip().lower()
        if text.startswith("yes"):
            return True
    return False
