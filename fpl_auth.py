"""
Authenticates against FPL using an OAuth2 refresh token, instead of
submitting your email/password directly.

Why the change: account.premierleague.com's login page is protected by
Cloudflare + DataDome bot detection — this actively fingerprints real
browsers (TLS handshake details, JS execution, behavioral signals) and
reliably blocks scripted form submissions no matter how correctly the
request is shaped. That's not a "get the payload right" problem, so
scripting the login form directly isn't viable. The token endpoint,
by contrast, is a machine-to-machine OAuth call and works cleanly with
plain HTTP requests — no browser fingerprint involved.

One-time manual setup: log in once in a real browser, capture the
refresh_token from the resulting /as/token response (via DevTools ->
Network, or a HAR export), and store it as the FPL_REFRESH_TOKEN
secret. This module exchanges that refresh token for a fresh access
token on every run — you should never need to repeat that manual
capture unless the token stops working entirely.

Two real things this doesn't yet resolve — flagged, not hidden:

1. REFRESH TOKEN ROTATION: some OAuth providers issue a NEW refresh
   token on every use, invalidating the old one. We don't yet know if
   Premier League's identity provider does this. If it does,
   FPL_REFRESH_TOKEN will need updating after every single run, which
   GitHub Actions can't do to its own secrets without extra setup. The
   code below detects and logs if this happens (never prints the
   actual new token) — the first real run will tell us whether this is
   a problem we need to solve.

2. WHETHER fantasy.premierleague.com's API (my-team, transfers)
   ACTUALLY ACCEPTS a Bearer access token, vs still requiring a
   cookie-based session set up through some other step. This flow was
   reverse-engineered from what the browser does, not from official
   docs — untested against those endpoints as of writing this. Test
   fpl_actions.get_current_squad() with a real session from this
   module before trusting the rest of the pipeline.
"""
from __future__ import annotations

import os

import requests

from network_utils import with_retry

TOKEN_URL = "https://account.premierleague.com/as/token"
CLIENT_ID = "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"  # public client ID, not a secret
REDIRECT_URI = "https://fantasy.premierleague.com/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class FPLAuthError(Exception):
    """Raised when token refresh fails or a required environment variable is missing."""


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise FPLAuthError(f"Missing required environment variable: {name}")
    return value


def login() -> requests.Session:
    """Exchange FPL_REFRESH_TOKEN for a fresh access token.

    Returns a requests.Session with the access token attached as a
    Bearer Authorization header — reuse it for subsequent calls rather
    than calling login() again.
    """
    refresh_token = _get_required_env("FPL_REFRESH_TOKEN")

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }

    response = with_retry(
        lambda: requests.post(
            TOKEN_URL,
            data=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://fantasy.premierleague.com",
                "referer": "https://fantasy.premierleague.com/",
                "user-agent": USER_AGENT,
            },
            timeout=15,
        ),
        what="FPL token refresh",
    )

    if response.status_code != 200:
        raise FPLAuthError(
            f"Token refresh failed with status {response.status_code}: "
            f"{response.text[:300]}"
        )

    tokens = response.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise FPLAuthError("Token refresh response had no access_token.")

    new_refresh_token = tokens.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        print(
            "[fpl_auth] NOTICE: the refresh token ROTATED on this call — "
            "a new one was issued and the old FPL_REFRESH_TOKEN secret is "
            "likely now invalid for future runs. It needs updating. "
            "(Value intentionally not printed here.)"
        )

    session = requests.Session()
    session.headers.update(
        {"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT}
    )
    return session


def get_team_id() -> str:
    return _get_required_env("FPL_TEAM_ID")
