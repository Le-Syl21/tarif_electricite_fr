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

# One time: "22:00", "22h30", "22H", "1h", "6". One range: two times joined by
# "-", "/", "à" or "a". Ranges are separated by ",", ";", "&" or "et".
_TIME = r"(\d{1,2})(?:\s*[:hH]\s*(\d{2})?)?"
_RANGE = re.compile(rf"^\s*{_TIME}\s*(?:-|/|à|a)\s*{_TIME}\s*$", re.IGNORECASE)
_SEPARATORS = re.compile(r"\s*(?:,|;|&|\bet\b)\s*", re.IGNORECASE)
# Enedis writes them "HC (22H30-6H30)" or "HC (2H00-7H00;13H00-16H00)".
_ENEDIS = re.compile(r"^\s*HC\s*\((.*)\)\s*$", re.IGNORECASE)


def parse_offpeak(text: str) -> list[tuple[time, time]]:
    """Parse off-peak hours as bills and customer areas write them.

    "22:00-06:00", "01:30-07:30, 12:30-14:30", "1h/7h30 & 13h/14h30" and
    Enedis' "HC (22H30-6H30)" are all accepted. Ranges may cross midnight.
    Raises ValueError on anything else.
    """
    if found := _ENEDIS.match(text):
        text = found.group(1)
    ranges = []
    for part in _SEPARATORS.split(text):
        if not part.strip():
            continue
        found = _RANGE.match(part)
        if not found:
            raise ValueError(f"not a time range: {part.strip()!r}")
        h1, m1, h2, m2 = (int(g or 0) for g in found.groups())
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


TEMPO_OFFPEAK = [(time(TEMPO_OFFPEAK_START_HOUR), time(TEMPO_DAY_START_HOUR))]


def offpeak_ranges(option: str, offpeak: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Off-peak ranges of an option: the customer's for HP/HC, fixed for Tempo."""
    if option == OPTION_BASE:
        return []
    if option == OPTION_HPHC:
        return offpeak
    return TEMPO_OFFPEAK


def next_change(now: datetime, ranges: list[tuple[time, time]]) -> datetime | None:
    """When off-peak next starts or ends after ``now``; None without ranges.

    Two ranges that touch (22:00-00:00 and 00:00-06:00) make one: only a real
    switch counts. Times are wall-clock times in ``now``'s time zone.
    """
    if not ranges:
        return None
    current = in_ranges(now.time(), ranges)
    bounds = sorted({t for pair in ranges for t in pair})
    for days in range(3):
        day = now.date() + timedelta(days=days)
        for bound in bounds:
            moment = datetime.combine(day, bound, tzinfo=now.tzinfo)
            if moment > now and in_ranges(bound, ranges) != current:
                return moment
    return None


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
    return f"{colour}_{'hc' if in_ranges(now.time(), TEMPO_OFFPEAK) else 'hp'}"
