from pathlib import Path

import pytest

from apple_refurb_reminder.apple import ObservationError, parse_catalog, parse_detail

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_realistic_catalog_bootstrap() -> None:
    values = parse_catalog((FIXTURES / "catalog.html").read_text())
    assert len(values) == 1
    assert values[0].id == "G1MLEJ/A"
    assert values[0].price_jpy == 455800
    assert values[0].url == "https://www.apple.com/jp/shop/product/g1mlej/a/example"


def test_parses_required_details() -> None:
    summary = parse_catalog((FIXTURES / "catalog.html").read_text())[0]
    value = parse_detail((FIXTURES / "detail.html").read_text(), summary)
    assert value.display_size_inches == 14
    assert value.chip == "M5 Pro"
    assert value.cpu_cores == 15
    assert value.gpu_cores == 16
    assert value.memory_gb == 48
    assert value.storage == "1TB"


def test_rejects_unknown_catalog_structure() -> None:
    with pytest.raises(ObservationError):
        parse_catalog("<html></html>")
