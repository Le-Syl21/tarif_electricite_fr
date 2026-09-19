"""Which pricing period applies at a given time."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from .const import (
    OPTION_BASE,
    OPTION_HPHC,
    TEMPO_DAY_START_HOUR,
    TEMPO_OFFPEAK_START_HOUR,
)

_RANGE = re.compile(r"^\s*(\d{1,2})[:h](\d{2})\s*-\s*(\d{1,2})[:h](\d{2})\s*$")


def parse_offpeak(text: str) -> list[tuple[time, time]]:
    """Parse off-peak hours such as "22:00-06:00" or "01:30-07:30, 12:30-14:30".

    Ranges may cross midnight. Raises ValueError on anything else.
    """
    ranges = []
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        found = _RANGE.match(part)
        if not found:
            raise ValueError(f"not a time range: {part.strip()!r}")
        h1, m1, h2, m2 = (int(g) for g in found.groups())
        start, end = time(h1, m1), time(h2, m2)  # time() rejects 24:00, 12:75...
        if start == end:
            raise ValueError(f"empty time range: {part.strip()!r}")
        ranges.append((start, end))
    if not ranges:
        raise ValueError("no off-peak range")
    return ranges


def in_ranges(moment: time, ranges: list[tuple[time, time]]) -> bool:
    for start, end in ranges:
        if start < end:
            if start <= moment < end:
                return True
        elif moment >= start or moment < end:  # crosses midnight
            return True
    return False


def tempo_day(now: datetime) -> date:
    """The Tempo day ``now`` belongs to: a Tempo day starts at 06:00."""
    if now.hour < TEMPO_DAY_START_HOUR:
        return now.date() - timedelta(days=1)
    return now.date()


def current_period(
    option: str,
    now: datetime,
    offpeak: list[tuple[time, time]],
    colours: dict[date, str],
) -> str | None:
    """Return the period in force (a key of PERIODS[option]), None if unknown.

    For Tempo the colour of the Tempo day is needed; without it the period is
    unknown rather than guessed.
    """
    if option == OPTION_BASE:
        return "base"
    if option == OPTION_HPHC:
        return "hc" if in_ranges(now.time(), offpeak) else "hp"
    colour = colours.get(tempo_day(now))
    if colour is None:
        return None
    offpeak_tempo = now.hour >= TEMPO_OFFPEAK_START_HOUR or now.hour < TEMPO_DAY_START_HOUR
    return f"{colour}_{'hc' if offpeak_tempo else 'hp'}"
