"""Off-peak hours, Tempo days and the period in force."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.tarif_electricite_fr.periods import (
    current_period,
    in_ranges,
    next_change,
    offpeak_ranges,
    parse_offpeak,
    tempo_day,
)
from custom_components.tarif_electricite_fr.tempo import quotas, remaining, season_of


def test_parse_offpeak_forms():
    assert parse_offpeak("22:00-06:00") == [(time(22), time(6))]
    assert parse_offpeak("1h30-7h30 ; 12:30 - 14:30") == [
        (time(1, 30), time(7, 30)),
        (time(12, 30), time(14, 30)),
    ]


def test_parse_offpeak_bill_forms():
    # SICAE ELY bill, "Tranche HC".
    assert parse_offpeak("1h/7h30 & 13h/14h30") == [
        (time(1), time(7, 30)),
        (time(13), time(14, 30)),
    ]
    assert parse_offpeak("22h à 6h et 12h30 à 14h30") == [
        (time(22), time(6)),
        (time(12, 30), time(14, 30)),
    ]


def test_parse_offpeak_enedis_form():
    assert parse_offpeak("HC (22H30-6H30)") == [(time(22, 30), time(6, 30))]
    assert parse_offpeak("HC (2H00-7H00;13H00-16H00)") == [
        (time(2), time(7)),
        (time(13), time(16)),
    ]


@pytest.mark.parametrize("text", ["", "25:00-06:00", "10:00-10:00", "22:00", "22h30", "1h/", "HC"])
def test_parse_offpeak_rejects(text):
    with pytest.raises(ValueError):
        parse_offpeak(text)


def test_ranges_cross_midnight():
    night = parse_offpeak("22:00-06:00")
    assert in_ranges(time(23, 59), night)
    assert in_ranges(time(0, 0), night)
    assert not in_ranges(time(6, 0), night)
    assert not in_ranges(time(21, 59), night)


def test_hphc_split_ranges():
    offpeak = parse_offpeak("01:30-07:30, 12:30-14:30")
    at = lambda h, m: current_period("hphc", datetime(2026, 9, 19, h, m), offpeak, {})
    assert at(13, 0) == "hc"
    assert at(15, 0) == "hp"
    assert at(7, 29) == "hc"


def test_tempo_day_starts_at_six():
    assert tempo_day(datetime(2026, 9, 19, 5, 59)) == date(2026, 9, 18)
    assert tempo_day(datetime(2026, 9, 19, 6, 0)) == date(2026, 9, 19)


def test_tempo_night_uses_previous_day_colour():
    colours = {date(2026, 12, 1): "rouge", date(2026, 12, 2): "bleu"}
    at = lambda d, h: current_period("tempo", datetime(2026, 12, d, h), [], colours)
    assert at(1, 10) == "rouge_hp"
    assert at(1, 23) == "rouge_hc"
    assert at(2, 3) == "rouge_hc"  # still the red day until 06:00
    assert at(2, 6) == "bleu_hp"


def test_tempo_unknown_colour_is_unknown():
    assert current_period("tempo", datetime(2026, 12, 3, 10), [], {}) is None


def test_base_is_always_base():
    assert current_period("base", datetime(2026, 12, 3, 3), [], {}) == "base"


def test_seasons_and_quotas():
    assert season_of(date(2026, 8, 31)) == "2025-2026"
    assert season_of(date(2026, 9, 1)) == "2026-2027"
    assert quotas("2026-2027") == {"bleu": 300, "blanc": 43, "rouge": 22}
    assert quotas("2027-2028")["bleu"] == 301  # February 2028


def test_remaining_counts_today():
    colours = {date(2026, 9, d): "bleu" for d in range(1, 21)}  # 20 is tomorrow
    colours[date(2026, 8, 31)] = "rouge"  # previous season
    assert remaining(colours, date(2026, 9, 19)) == {"bleu": 281, "blanc": 43, "rouge": 22}


PARIS = ZoneInfo("Europe/Paris")


def test_next_change_bill_ranges():
    ranges = parse_offpeak("1h/7h30 & 13h/14h30")
    at = lambda h, m: next_change(datetime(2026, 9, 19, h, m, tzinfo=PARIS), ranges)
    assert at(0, 30) == datetime(2026, 9, 19, 1, 0, tzinfo=PARIS)
    assert at(3, 0) == datetime(2026, 9, 19, 7, 30, tzinfo=PARIS)
    assert at(14, 30) == datetime(2026, 9, 20, 1, 0, tzinfo=PARIS)


def test_next_change_touching_ranges_are_one():
    ranges = parse_offpeak("22:00-00:00, 00:00-06:00")
    assert next_change(datetime(2026, 9, 19, 23, 0, tzinfo=PARIS), ranges) == datetime(
        2026, 9, 20, 6, 0, tzinfo=PARIS
    )


def test_next_change_tempo_and_base():
    tempo = offpeak_ranges("tempo", [])
    assert next_change(datetime(2026, 12, 1, 23, 0, tzinfo=PARIS), tempo) == datetime(
        2026, 12, 2, 6, 0, tzinfo=PARIS
    )
    assert (
        next_change(datetime(2026, 12, 1, 23, 0, tzinfo=PARIS), offpeak_ranges("base", [])) is None
    )


def test_next_change_across_dst():
    # 25 October 2026: clocks go back at 03:00; off-peak still ends at 06:00 local.
    end = next_change(datetime(2026, 10, 24, 23, 0, tzinfo=PARIS), offpeak_ranges("tempo", []))
    assert end == datetime(2026, 10, 25, 6, 0, tzinfo=PARIS)
    assert end.utcoffset().total_seconds() == 3600
