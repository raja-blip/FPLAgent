"""
Deadline-window detection for the T-24h/T-3h loop.

Deliberately a wide window, not a precise instant — the workflows that
call this run periodically (every couple hours, see the .yml files),
not at an exact minute, since FPL deadlines shift week to week and
aren't expressible as a fixed weekly cron time. Idempotency (not
re-proposing/re-executing) is handled separately via agent_state, not
by narrowing this window — a wide, generous window plus a state check
is far more robust than trying to hit an exact moment.
"""
from __future__ import annotations

PROPOSE_WINDOW_HOURS = (20.0, 28.0)  # propose when deadline is 20-28h away
EXECUTE_WINDOW_HOURS = (1.0, 5.0)  # execute when deadline is 1-5h away


def hours_until(deadline_epoch: int, now: float) -> float:
    return (deadline_epoch - now) / 3600.0


def in_propose_window(deadline_epoch: int, now: float) -> bool:
    h = hours_until(deadline_epoch, now)
    return PROPOSE_WINDOW_HOURS[0] <= h <= PROPOSE_WINDOW_HOURS[1]


def in_execute_window(deadline_epoch: int, now: float) -> bool:
    h = hours_until(deadline_epoch, now)
    return EXECUTE_WINDOW_HOURS[0] <= h <= EXECUTE_WINDOW_HOURS[1]
