"""Regulated "Tarif Bleu" prices: CRE open data, EDF's PDF grid, and which one applies.

Nothing here depends on Home Assistant, so it can be tested on its own.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime

from .const import OPTION_BASE, OPTION_HPHC, OPTION_TEMPO, PERIODS, POWERS

SOURCE_CRE = "cre"
SOURCE_EDF = "edf"


@dataclass(frozen=True)
class Tariff:
    """Prices of one option and one subscribed power, all taxes included."""

    option: str
    power: int
    valid_from: date
    subscription_monthly: float  # EUR per month
    prices: dict[str, float] = field(default_factory=dict)  # EUR per kWh, by period
    source: str = SOURCE_CRE

    def as_dict(self) -> dict:
        data = asdict(self)
        data["valid_from"] = self.valid_from.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Tariff:
        return cls(**{**data, "valid_from": date.fromisoformat(data["valid_from"])})


class GridError(ValueError):
    """A price source did not have the expected shape."""


def _number(text: str) -> float:
    return float(text.strip().replace(",", "."))


# --- CRE open data -----------------------------------------------------------

# Column holding the price of each period, TTC, in the CRE file of each option.
_CRE_COLUMNS = {
    OPTION_BASE: {"base": "PART_VARIABLE_TTC"},
    OPTION_HPHC: {"hp": "PART_VARIABLE_HP_TTC", "hc": "PART_VARIABLE_HC_TTC"},
    OPTION_TEMPO: {
        f"{colour}_{slot}": f"PART_VARIABLE_{slot.upper()}{cre}_TTC"
        for colour, cre in (("bleu", "Bleu"), ("blanc", "Blanc"), ("rouge", "Rouge"))
        for slot in ("hc", "hp")
    },
}


def parse_cre(text: str, option: str, power: int, today: date) -> Tariff | None:
    """Return the CRE tariff in force on ``today``, or None if the file has none.

    Each row is valid from DATE_DEBUT to DATE_FIN, both inclusive; the row in
    force has no DATE_FIN yet. Old rows can have empty prices for powers that
    did not exist at the time.
    """
    columns = _CRE_COLUMNS[option]
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    missing = {"DATE_DEBUT", "DATE_FIN", "P_SOUSCRITE", "PART_FIXE_TTC", *columns.values()}
    missing -= set(reader.fieldnames or ())
    if missing:
        raise GridError(f"CRE file for {option} lacks columns {sorted(missing)}")

    for row in reader:
        try:
            if int(row["P_SOUSCRITE"]) != power:
                continue
            start = datetime.strptime(row["DATE_DEBUT"], "%d/%m/%Y").date()
            end = row["DATE_FIN"].strip()
            if start > today or (end and datetime.strptime(end, "%d/%m/%Y").date() < today):
                continue
            return Tariff(
                option=option,
                power=power,
                valid_from=start,
                subscription_monthly=round(_number(row["PART_FIXE_TTC"]) / 12, 2),
                prices={period: _number(row[col]) for period, col in columns.items()},
                source=SOURCE_CRE,
            )
        except ValueError:
            # A malformed or empty row: skip it, another one may be in force.
            continue
    return None


# --- EDF price grid (PDF) ----------------------------------------------------

_MONTHS = (
    "janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre"
).split()
_APPLICABLE = re.compile(r"Applicable au (\d{1,2})(?:er)? (\w+) (\d{4})", re.IGNORECASE)
_CELL_NUMBER = re.compile(r"^\d+(?:,\d+)?$")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


def parse_edf_tables(
    text: str, tables: list[list[list[str | None]]]
) -> dict[str, dict[int, Tariff]]:
    """Read the tables pdfplumber found on the first page of EDF's grid.

    ``text`` is the page text (for the "Applicable au" date). Every row whose
    number cells are the power, the monthly subscription and one price (cts €
    per kWh) per period is a price row; merged cells show up as None or empty
    strings in varying columns, so only the numbers are kept, in order.
    """
    found = _APPLICABLE.search(text)
    if not found:
        raise GridError("EDF grid has no 'Applicable au' date")
    day, month, year = found.groups()
    try:
        valid_from = date(int(year), _MONTHS.index(_plain(month)) + 1, int(day))
    except ValueError as err:
        raise GridError(f"EDF grid date not understood: {found.group(0)!r}") from err

    grid: dict[str, dict[int, Tariff]] = {OPTION_BASE: {}, OPTION_HPHC: {}, OPTION_TEMPO: {}}
    for table in tables:
        title = _plain((table[0][0] or "") if table and table[0] else "")
        if "tempo" in title:
            option = OPTION_TEMPO
        elif "creuses" in title:
            option = OPTION_HPHC
        elif "base" in title:
            option = OPTION_BASE
        else:
            continue
        periods = PERIODS[option]
        for row in table:
            cells = [c.strip() for c in row if c and _CELL_NUMBER.match(c.strip())]
            if len(cells) != 2 + len(periods):
                continue
            power, subscription, *cents = cells
            grid[option][int(power)] = Tariff(
                option=option,
                power=int(power),
                valid_from=valid_from,
                subscription_monthly=_number(subscription),
                prices={p: round(_number(c) / 100, 6) for p, c in zip(periods, cents, strict=True)},
                source=SOURCE_EDF,
            )

    # A layout change must not feed wrong prices: every power of every option
    # has to be there, and nothing else.
    for option, tariffs in grid.items():
        if sorted(tariffs) != sorted(POWERS[option]):
            raise GridError(
                f"EDF grid layout changed: {option} has powers {sorted(tariffs)}, "
                f"expected {list(POWERS[option])}"
            )
    return grid


def parse_edf_pdf(content: bytes) -> dict[str, dict[int, Tariff]]:
    """Extract every tariff of EDF's "Grille_prix_Tarif_Bleu.pdf" (blocking)."""
    import pdfplumber  # noqa: PLC0415 - heavy import, only needed here

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        page = pdf.pages[0]
        return parse_edf_tables(page.extract_text() or "", page.extract_tables())


# --- Which one applies -------------------------------------------------------


def choose(cre: Tariff | None, edf: Tariff | None, today: date) -> Tariff | None:
    """Pick the tariff to use on ``today``.

    The CRE file is the reference. EDF's grid takes over when the CRE has no
    row for this power (Base 18-36 kVA) or when it is newer than the CRE row and
    already in force: a price change the CRE has not published yet.

    When both cover the same period, the subscription comes from EDF: the CRE
    publishes a yearly amount whose taxes differ by a few cents a month from
    the monthly amount EDF bills.
    """
    if edf is not None and edf.valid_from > today:
        edf = None
    if cre is None:
        return edf
    if edf is None or edf.valid_from < cre.valid_from:
        return cre
    if edf.valid_from > cre.valid_from:
        return edf
    return replace(cre, subscription_monthly=edf.subscription_monthly)
