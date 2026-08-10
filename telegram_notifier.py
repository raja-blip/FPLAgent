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

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    response = requests.post(
        TELEGRAM_API.format(token=token),
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    response.raise_for_status()
