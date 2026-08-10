"""
Shared retry helper for network calls.

GitHub's hosted Actions runners have a documented, recurring class of
intermittent DNS resolution flakiness — it's not specific to FPL's
domains, similar reports show up across many unrelated projects'
workflows. A few retries with a short backoff is the standard
mitigation: cheap, and it turns a one-off blip into a non-event instead
of a failed gameweek run that nobody's watching to manually retry.

This does NOT paper over a persistent or structural failure — after
MAX_ATTEMPTS, the original exception still propagates. A real outage or
a genuinely broken endpoint still surfaces as an error rather than
silently hanging or pretending to succeed.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")

MAX_ATTEMPTS = 4
BASE_DELAY_SECONDS = 2  # doubles each retry: 2s, 4s, 8s


def with_retry(func: Callable[[], T], *, what: str = "request") -> T:
    """Call func(), retrying on connection/DNS errors with exponential backoff.

    Only retries on requests.exceptions.ConnectionError — the exact
    exception type the DNS failure we saw actually raised. A real HTTP
    error response (bad credentials, 4xx/5xx) is not a transient network
    issue and is not caught here, since retrying it wouldn't help and
    would just delay surfacing a real failure.
    """
    last_exception: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return func()
        except requests.exceptions.ConnectionError as exc:
            last_exception = exc
            if attempt == MAX_ATTEMPTS:
                break
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            print(
                f"[retry] {what} failed (attempt {attempt}/{MAX_ATTEMPTS}): "
                f"{exc}. Retrying in {delay}s..."
            )
            time.sleep(delay)

    assert last_exception is not None
    raise last_exception
