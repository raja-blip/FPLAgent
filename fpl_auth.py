"""
Authenticates against FPL's (unofficial, undocumented) login flow to get
a session that can read your private squad and submit changes.

This mimics what your browser does on login — FPL doesn't publish an
official API for it. The endpoint and payload shape below are the
pattern the FPL bot community has used for years (the open-source
"Robo Klopp" project is one public example), not something guessed from
nothing — but it genuinely is unofficial: FPL could change it without
notice, and I can't test this against the live endpoint myself, since
users.premierleague.com is outside what I can reach from this sandbox.
Run this for real yourself (with --dry-run first) before trusting it.

Credentials are read from environment variables only — this module
never accepts them as function arguments, logs them, or writes them
anywhere.
"""
from __future__ import annotations

import os

import requests

LOGIN_URL = "https://users.premierleague.com/accounts/login/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class FPLAuthError(Exception):
    """Raised when login fails or a required environment variable is missing."""


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise FPLAuthError(f"Missing required environment variable: {name}")
    return value


def login() -> requests.Session:
    """Log in using FPL_EMAIL / FPL_PASSWORD from the environment.

    Returns an authenticated requests.Session — reuse it for every
    subsequent call (reading your squad, submitting transfers, etc.)
    rather than logging in again each time.
    """
    email = _get_required_env("FPL_EMAIL")
    password = _get_required_env("FPL_PASSWORD")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    payload = {
        "login": email,
        "password": password,
        "app": "plfpl-web",
        "redirect_uri": "https://fantasy.premierleague.com/a/login",
    }

    response = session.post(LOGIN_URL, data=payload, timeout=15)

    # FPL's login doesn't return a clean JSON success/failure flag — a
    # successful login sets a session cookie, so that's what we check for
    # rather than trusting the HTTP status code alone.
    if "pl_profile" not in session.cookies.get_dict():
        raise FPLAuthError(
            "Login did not produce a session cookie — check your "
            "credentials, or FPL may have changed their login flow."
        )

    return session


def get_team_id() -> str:
    return _get_required_env("FPL_TEAM_ID")
