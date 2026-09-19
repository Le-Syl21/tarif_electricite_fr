"""CRE file, EDF grid and the choice between them."""

from dataclasses import replace
from datetime import date

import pytest

from custom_components.tarif_electricite_fr.const import POWERS
from custom_components.tarif_electricite_fr.prices import (
    SOURCE_CRE,
    SOURCE_EDF,
    GridError,
    Tariff,
    choose,
    parse_cre,
    parse_edf_tables,
)

from .conftest import cre_text, edf_page

AUG_2026 = date(2026, 9, 19)


def test_cre_base_in_force():
    tariff = parse_cre(cre_text("base"), "base", 6, AUG_2026)
    assert tariff.valid_from == date(2026, 8, 1)
    assert tariff.prices == {"base": 0.2001}
    assert tariff.subscription_monthly == pytest.approx(190.81 / 12, abs=0.005)
    assert tariff.source == SOURCE_CRE


def test_cre_end_date_is_inclusive():
    # The 01/02/2026 row ends on 31/07/2026: still in force that day.
    tariff = parse_cre(cre_text("hphc"), "hphc", 6, date(2026, 7, 31))
    assert tariff.valid_from == date(2026, 2, 1)
    tariff = parse_cre(cre_text("hphc"), "hphc", 6, date(2026, 8, 1))
    assert tariff.valid_from == date(2026, 8, 1)
    assert tariff.prices == {"hp": 0.2142, "hc": 0.1589}


def test_cre_tempo_columns():
    tariff = parse_cre(cre_text("tempo"), "tempo", 9, AUG_2026)
    assert tariff.prices == {
        "bleu_hc": 0.1356,
        "bleu_hp": 0.1654,
        "blanc_hc": 0.1536,
        "blanc_hp": 0.1921,
        "rouge_hc": 0.1615,
        "rouge_hp": 0.7295,
    }


def test_cre_has_no_base_above_15_kva():
    assert parse_cre(cre_text("base"), "base", 18, AUG_2026) is None


def test_cre_empty_old_rows_are_skipped():
    # 2016 Tempo 6 kVA has empty prices: nothing in force, no crash.
    assert parse_cre(cre_text("tempo"), "tempo", 6, date(2016, 9, 1)) is None


def test_cre_wrong_file_is_refused():
    with pytest.raises(GridError):
        parse_cre(cre_text("base"), "tempo", 6, AUG_2026)


def test_edf_grid_matches_cre():
    page = edf_page()
    grid = parse_edf_tables(page["text"], page["tables"])
    for option, powers in POWERS.items():
        assert sorted(grid[option]) == sorted(powers)
        for power in powers:
            edf = grid[option][power]
            assert edf.valid_from == date(2026, 8, 1)
            assert edf.source == SOURCE_EDF
            cre = parse_cre(cre_text(option), option, power, AUG_2026)
            if cre is not None:
                assert edf.prices == pytest.approx(cre.prices, abs=1e-9)
    assert grid["base"][36].subscription_monthly == 53.88
    assert grid["tempo"][6].prices["rouge_hp"] == pytest.approx(0.7295)


def test_edf_grid_missing_row_is_refused():
    page = edf_page()
    tables = [list(t) for t in page["tables"]]
    tables[2] = tables[2][:-1]  # drop Tempo 36 kVA
    with pytest.raises(GridError, match="tempo"):
        parse_edf_tables(page["text"], tables)


def test_edf_grid_without_date_is_refused():
    with pytest.raises(GridError):
        parse_edf_tables("no date here", edf_page()["tables"])


def _tariff(source: str, valid_from: date) -> Tariff:
    return Tariff("base", 6, valid_from, 15.0, {"base": 0.2}, source)


def test_choose_prefers_cre_with_edf_subscription():
    cre = _tariff(SOURCE_CRE, date(2026, 8, 1))
    edf = replace(
        _tariff(SOURCE_EDF, date(2026, 8, 1)), subscription_monthly=14.9, prices={"base": 0.3}
    )
    chosen = choose(cre, edf, AUG_2026)
    assert chosen.source == SOURCE_CRE
    assert chosen.prices == cre.prices
    assert chosen.subscription_monthly == 14.9


def test_choose_older_edf_grid_is_ignored():
    cre = _tariff(SOURCE_CRE, date(2026, 8, 1))
    edf = replace(_tariff(SOURCE_EDF, date(2026, 2, 1)), subscription_monthly=14.9)
    assert choose(cre, edf, AUG_2026) is cre


def test_choose_newer_edf_grid_wins():
    cre = _tariff(SOURCE_CRE, date(2026, 2, 1))
    edf = _tariff(SOURCE_EDF, date(2026, 8, 1))
    assert choose(cre, edf, AUG_2026) is edf


def test_choose_future_edf_grid_waits():
    cre = _tariff(SOURCE_CRE, date(2026, 8, 1))
    edf = _tariff(SOURCE_EDF, date(2027, 2, 1))
    assert choose(cre, edf, AUG_2026) is cre
    assert choose(None, edf, AUG_2026) is None


def test_choose_edf_fills_missing_power():
    edf = _tariff(SOURCE_EDF, date(2026, 8, 1))
    assert choose(None, edf, AUG_2026) is edf


def test_tariff_round_trip():
    tariff = replace(_tariff(SOURCE_EDF, date(2026, 8, 1)), prices={"hp": 0.2142, "hc": 0.1589})
    assert Tariff.from_dict(tariff.as_dict()) == tariff
