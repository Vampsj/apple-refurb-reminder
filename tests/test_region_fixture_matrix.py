from __future__ import annotations

import json
from pathlib import Path

import pytest

from apple_refurb_reminder.apple import (
    ObservationError,
    listing_from_summary,
    parse_catalog,
)
from apple_refurb_reminder.models import ProductCategory

FIXTURE = Path(__file__).parent / "fixtures/regions/catalog_matrix.json"
CASES = json.loads(FIXTURE.read_text())


def catalog_html(case: dict[str, object], *, part_number: str = "TEST") -> str:
    payload = {
        "tiles": [
            {
                "title": case["title"],
                "partNumber": part_number,
                "productDetailsUrl": f"/shop/product/{part_number.lower()}",
                "price": {"currentPrice": {"raw_amount": "1234"}},
                "filters": {"dimensions": case["dimensions"]},
            }
        ]
    }
    return f"<script>window.REFURB_GRID_BOOTSTRAP = {json.dumps(payload)};</script>"


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[f"{case['region']}-{case['category']}" for case in CASES],
)
def test_region_and_category_fixture(case: dict[str, object]) -> None:
    category = ProductCategory(str(case["category"]))
    summary = parse_catalog(
        catalog_html(case),
        category=category,
        base_url=str(case["base_url"]),
        currency=str(case["currency"]),
    )[0]
    listing = listing_from_summary(summary)
    assert listing.product == case["expected_model"]
    assert listing.category == category
    assert listing.currency == case["currency"]
    assert listing.storage is not None
    assert listing.url.startswith(str(case["base_url"]))


def test_duplicate_product_ids_are_a_catalog_failure() -> None:
    case = CASES[0]
    tile = json.loads(
        catalog_html(case).split(" = ", 1)[1].rsplit(";</script>", 1)[0]
    )["tiles"][0]
    html = (
        "<script>window.REFURB_GRID_BOOTSTRAP = "
        f"{json.dumps({'tiles': [tile, tile]})};</script>"
    )
    with pytest.raises(ObservationError, match="Duplicate"):
        parse_catalog(html)


def test_implausibly_large_catalog_is_rejected() -> None:
    html = (
        "<script>window.REFURB_GRID_BOOTSTRAP = "
        f"{json.dumps({'tiles': [{}] * 1001})};</script>"
    )
    with pytest.raises(ObservationError, match="unexpectedly high"):
        parse_catalog(html)
