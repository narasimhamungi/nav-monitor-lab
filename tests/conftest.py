from datetime import date
from pathlib import Path

import pytest

from navmonitorlab import config
from navmonitorlab.sources import PriceBook
from navmonitorlab.sources.files import FileHoldings, FilePrices, FileTrackRecord

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def cfg():
    return config.load(ROOT / "configs")


@pytest.fixture(scope="session")
def snaps():
    return FileHoldings(SAMPLE / "holdings_nbpe.csv", SAMPLE / "snapshots_nbpe.csv").load()


@pytest.fixture(scope="session")
def track():
    return FileTrackRecord(SAMPLE / "track_record_calpers.csv").load()


@pytest.fixture(scope="session")
def prices():
    src, book = FilePrices(SAMPLE / "prices.csv"), PriceBook()
    for sym in src.symbols():
        book.add(sym, src.history(sym, date(1990, 1, 1), date(2100, 1, 1)), src.currency.get(sym, ""))
    return book


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
