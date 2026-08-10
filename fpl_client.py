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
from network_utils import with_retry

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
        response = with_retry(lambda: requests.get(url, timeout=10), what=f"GET {path}")
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


def get_last_season_output_rates() -> dict[int, float]:
    """Per-player last-season expected-goal-involvement rate, per 90 mins.

    FPL's live 'elements' data resets goals/assists/xG to zero at the
    start of each season, so pre-season (and early season, before a
    player's built up many minutes) there's no current-season signal at
    all to project from. This pulls each player's most recent past-season
    totals via element-summary and computes a per-90 rate ourselves,
    since history_past only has season-cumulative totals — confirmed via
    a real diagnostic run, not assumed (see scripts/inspect_player_history.py).

    Cached aggressively (180 days): this is historical data that only
    changes once a year at season rollover, and this makes one API call
    PER PLAYER (~700), which is slow enough you don't want to repeat it
    on every run.

    Players with no history_past (new to the league — rookies, new
    signings from outside the PL) get 0.0: an honest "no data" rather
    than a guessed number. That does mean brand-new players are
    underrated pre-season — a known, flagged limitation, not a silent one.
    """
    cache_file = CACHE_DIR / "last_season_rates.json"
    CACHE_DIR.mkdir(exist_ok=True, parents=True)

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 60 * 60 * 24 * 180:  # 180 days
            return {int(k): v for k, v in json.loads(cache_file.read_text()).items()}

    players = get_players()
    rates: dict[int, float] = {}

    for player in players:
        url = f"{BASE_URL}/element-summary/{player.id}/"
        try:
            response = with_retry(
                lambda u=url: requests.get(u, timeout=15),
                what=f"element-summary/{player.id}",
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            rates[player.id] = 0.0
            continue

        history_past = data.get("history_past", [])
        if not history_past:
            rates[player.id] = 0.0
            continue

        most_recent = history_past[-1]
        minutes = most_recent.get("minutes", 0) or 0
        try:
            egi = float(most_recent.get("expected_goal_involvements", 0.0) or 0.0)
        except (TypeError, ValueError):
            egi = 0.0

        rates[player.id] = (egi / minutes * 90) if minutes > 0 else 0.0

    cache_file.write_text(json.dumps(rates))
    return rates
