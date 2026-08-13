"""
Account actions against FPL: reading your current private squad, and
submitting transfers, starting XI, captain, and vice-captain.

This module doesn't decide *whether* to actually submit anything — the
dry-run/confirm safety switch lives entirely in the orchestration script
(plan.py / execute.py), not scattered across individual action
functions, so it stays in one obvious, auditable place.
"""
from __future__ import annotations

import requests

from network_utils import with_retry

TEAM_API = "https://fantasy.premierleague.com/api/my-team/{team_id}/"
TRANSFERS_API = "https://fantasy.premierleague.com/api/transfers/"


def get_current_squad(session: requests.Session, team_id: str) -> dict:
    """Your private squad, bank balance, and free transfers. Requires login()."""
    response = with_retry(
        lambda: session.get(TEAM_API.format(team_id=team_id), timeout=15),
        what="get_current_squad",
    )
    response.raise_for_status()
    return response.json()


def submit_transfers(
    session: requests.Session,
    team_id: str,
    transfers_out: list[int],
    transfers_in: list[int],
    current_gameweek: int,
) -> dict:
    """Submit a set of transfers.

    transfers_out and transfers_in must be the same length and paired by
    list position (transfers_out[i] is replaced by transfers_in[i]) —
    the caller (plan.py) is responsible for that pairing.
    """
    if len(transfers_out) != len(transfers_in):
        raise ValueError("transfers_out and transfers_in must be the same length")

    payload = {
        "confirmed": True,
        "entry": int(team_id),
        "event": current_gameweek,
        "transfers": [
            {
                "element_in": in_id,
                "element_out": out_id,
                "purchase_price": None,  # FPL fills this in server-side
                "selling_price": None,
            }
            for out_id, in_id in zip(transfers_out, transfers_in)
        ],
    }
    response = with_retry(
        lambda: session.post(TRANSFERS_API, json=payload, timeout=15),
        what="submit_transfers",
    )
    response.raise_for_status()
    return response.json()


def submit_lineup(
    session: requests.Session,
    team_id: str,
    starting_ids: list[int],
    bench_ids: list[int],
    captain_id: int,
    vice_captain_id: int,
    chip: str | None = None,
) -> dict:
    """Submit starting XI, bench order, captain, and vice-captain in one call.

    chip: one of "wildcard", "freehit", "bboost", "3xc" (FPL's own short
    codes — see UNVERIFIED note below) to activate that chip alongside
    this lineup submission, or None for a normal lineup-only submission.

    UNVERIFIED — flagged plainly, same as fpl_auth.py was before its
    first live test: this assumes chip activation works by including a
    "chip" key in the same POST as picks, based on the general shape of
    community-documented FPL bot projects, NOT confirmed against the
    live endpoint ourselves. This has never been tested with a real
    chip on a real account. Test with a low-stakes chip activation (or
    at minimum a dry run you inspect closely) before trusting this for
    real, especially for Wildcard/Free Hit, which can't be undone if
    this sends something wrong.
    """
    picks = [
        {
            "element": player_id,
            "position": position,
            "is_captain": player_id == captain_id,
            "is_vice_captain": player_id == vice_captain_id,
        }
        for position, player_id in enumerate(starting_ids + bench_ids, start=1)
    ]

    payload: dict = {"picks": picks}
    if chip is not None:
        payload["chip"] = chip

    response = with_retry(
        lambda: session.post(
            TEAM_API.format(team_id=team_id), json=payload, timeout=15
        ),
        what="submit_lineup",
    )
    response.raise_for_status()
    return response.json()
