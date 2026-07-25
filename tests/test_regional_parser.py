import json

import pytest

from apple_refurb_reminder.apple import AppleRegionalAdapter, listing_from_summary, parse_catalog
from apple_refurb_reminder.models import ProductCategory, Region, WatchRule


def catalog_html(title: str, dimensions: dict[str, str]) -> str:
    payload = {
        "tiles": [
            {
                "title": title,
                "partNumber": "TEST1LL/A",
                "productDetailsUrl": "/shop/product/test",
                "price": {"currentPrice": {"raw_amount": "1299.00"}},
                "filters": {"dimensions": dimensions},
            }
        ]
    }
    return f"<script>window.REFURB_GRID_BOOTSTRAP = {json.dumps(payload)};</script>"


@pytest.mark.parametrize(
    ("category", "title", "dimensions", "model", "storage"),
    [
        (
            ProductCategory.MAC,
            "Refurbished 14-inch MacBook Pro Apple M4 Pro chip with "
            "12-Core CPU and 16-Core GPU - Silver",
            {
                "dimensionScreensize": "14inch",
                "dimensionCapacity": "1tb",
                "tsMemorySize": "24gb",
                "dimensionColor": "silver",
            },
            "MacBook Pro",
            "1TB",
        ),
        (
            ProductCategory.IPHONE,
            "Refurbished iPhone 16 Pro 256GB - Black Titanium (Unlocked)",
            {"dimensionCapacity": "256gb", "dimensionColor": "blacktitanium"},
            "iPhone 16 Pro",
            "256GB",
        ),
        (
            ProductCategory.IPAD,
            "翻新 iPad Air 11 英寸无线局域网机型 128GB - 蓝色",
            {
                "dimensionCapacity": "128gb",
                "dimensionScreensize": "11inch",
                "dimensionconnectivity": "wifi",
                "dimensionColor": "blue",
            },
            "iPad Air 11 英寸",
            "128GB",
        ),
    ],
)
def test_catalog_dimensions_create_prefilterable_listing(
    category: ProductCategory,
    title: str,
    dimensions: dict[str, str],
    model: str,
    storage: str,
) -> None:
    summary = parse_catalog(
        catalog_html(title, dimensions),
        category=category,
        currency="USD",
    )[0]
    listing = listing_from_summary(summary)
    assert listing.product == model
    assert listing.storage == storage
    assert listing.currency == "USD"


def test_adapter_fetches_only_categories_used_by_rules() -> None:
    calls: list[str] = []
    html = catalog_html(
        "Refurbished iPhone 16 Pro 256GB - Black Titanium",
        {"dimensionCapacity": "256gb"},
    )

    def fetcher(url: str) -> str:
        calls.append(url)
        return html

    rules = (
        WatchRule("one", ProductCategory.IPHONE, "iPhone 16 Pro"),
        WatchRule("two", ProductCategory.IPHONE, "iPhone 16"),
    )
    summaries, listings, errors = AppleRegionalAdapter(
        Region.US, rules, fetcher=fetcher
    ).observe()
    assert calls == ["https://www.apple.com/shop/refurbished/iphone"]
    assert len(summaries) == len(listings) == 1
    assert errors == {}


def test_one_category_failure_does_not_discard_another() -> None:
    rules = (
        WatchRule("mac", ProductCategory.MAC, "MacBook Pro"),
        WatchRule("ipad", ProductCategory.IPAD, "iPad Pro"),
    )

    def fetcher(url: str) -> str:
        if url.endswith("/ipad"):
            raise TimeoutError("timed out")
        return catalog_html(
            "Refurbished 14-inch MacBook Pro Apple M4 chip",
            {"dimensionCapacity": "1tb"},
        )

    summaries, listings, errors = AppleRegionalAdapter(
        Region.HK, rules, fetcher=fetcher
    ).observe()
    assert len(summaries) == len(listings) == 1
    assert "category:ipad" in errors


def test_accessories_are_excluded_from_supported_product_category() -> None:
    html = catalog_html(
        "Refurbished Apple Pencil (USB-C)",
        {"refurbClearModel": "ipadaccessories"},
    )
    rule = WatchRule("ipad", ProductCategory.IPAD, "iPad Pro")
    summaries, listings, errors = AppleRegionalAdapter(
        Region.CN, (rule,), fetcher=lambda _url: html
    ).observe()
    assert summaries == []
    assert listings == []
    assert errors == {}
