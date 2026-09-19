"""Shared fixtures."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def cre_text(option: str) -> str:
    name = {"base": "Base", "hphc": "HPHC", "tempo": "Tempo"}[option]
    return (FIXTURES / f"Option_{name}.csv").read_text(encoding="utf-8")


def edf_page() -> dict:
    return json.loads((FIXTURES / "edf_grid_2026-08-01.json").read_text(encoding="utf-8"))
