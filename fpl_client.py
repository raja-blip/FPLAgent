"""
Thin client for the official (public, read-only) FPL API endpoints.

fantasy.premierleague.com isn't documented by the Premier League as a
public API, but bootstrap-static and fixtures are well-established,
widely-used, unauthenticated read endpoints in the FPL community. This
client only reads data — it never logs in and never changes anything on
your account. Account actions (transfers, chip usage) belong in a
separate module we'll build later, and that one *does* need your
credentials — this one deliberately doesn't.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import requests

from models import Fixture, Gameweek, Player, Team

BASE_URL = "https://fantasy.premierleague.com/api"
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_TTL_SECONDS = 60 * 30  # 30 minutes — plenty fresh for gameweek planning


class FPLClientError(Exception):
    """Raised when the FPL API can't be reached and no cached fallback exists."""


def _cached_get(path: str, cache_key: str) -> dict | list:
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    url = f"{BASE_URL}/{path}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        if cache_file.exists():
            # Stale data beats no data — better to plan off a 40-minute-old
            # snapshot than to crash right before a deadline.
            return json.loads(cache_file.read_text())
        raise FPLClientError(f"Failed to fetch {url}: {exc}") from exc

    cache_file.write_text(json.dumps(data))
    return data


def get_bootstrap_static() -> dict:
    """Raw bootstrap-static payload: players, teams, gameweeks, and more."""
    return _cached_get("bootstrap-static/", "bootstrap_static")


def get_fixtures() -> list[dict]:
    """Raw fixtures payload for the full season."""
    data = _cached_get("fixtures/", "fixtures")
    return data if isinstance(data, list) else []


def get_teams() -> list[Team]:
    data = get_bootstrap_static()
    return [Team(**t) for t in data["teams"]]


def get_gameweeks() -> list[Gameweek]:
    data = get_bootstrap_static()
    return [Gameweek(**e) for e in data["events"]]


def get_current_gameweek() -> Optional[Gameweek]:
    return next((gw for gw in get_gameweeks() if gw.is_current), None)


def get_next_gameweek() -> Optional[Gameweek]:
    return next((gw for gw in get_gameweeks() if gw.is_next), None)


def get_players() -> list[Player]:
    data = get_bootstrap_static()
    return [Player(**p) for p in data["elements"]]


def get_all_fixtures() -> list[Fixture]:
    return [Fixture(**f) for f in get_fixtures()]
