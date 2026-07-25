import json

import pytest

from apple_refurb_reminder.apple import (
    AppleRegionalAdapter,
    listing_from_summary,
    parse_catalog,
    parse_regional_detail,
)
from apple_refurb_reminder.models import (
    ListingSummary,
    ProductCategory,
    Region,
    WatchRule,
)


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


def test_detail_is_shared_across_rules_and_then_cached() -> None:
    catalog = catalog_html(
        "Refurbished MacBook Pro",
        {"dimensionCapacity": "1tb"},
    )
    detail = """
    <meta name="description" content="14-inch, Apple M4 Pro chip,
    12-Core CPU, 16-Core GPU, 24GB unified memory, 1TB SSD">
    <script type="application/ld+json">
    {"@type":"Product","name":"Refurbished 14-inch MacBook Pro",
    "url":"https://www.apple.com/shop/product/test"}
    </script>
    """
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        return catalog if "refurbished" in url else detail

    rules = (
        WatchRule("memory", ProductCategory.MAC, "MacBook Pro", memory_gb=24),
        WatchRule("cpu", ProductCategory.MAC, "MacBook Pro", cpu_cores=12),
    )
    cache: dict[str, dict[str, object]] = {}
    adapter = AppleRegionalAdapter(Region.US, rules, fetcher=fetcher)
    summaries, listings, errors = adapter.observe(cache=cache)
    assert len(calls) == 2
    assert listings[0].memory_gb == 24
    assert errors == {}
    calls.clear()
    adapter.observe(cache=cache, previous_catalog_ids={summaries[0].id})
    assert calls == ["https://www.apple.com/shop/refurbished/mac"]


def test_cached_detail_refreshes_after_reappearance() -> None:
    catalog = catalog_html("Refurbished MacBook Pro", {})
    detail_calls = 0

    def fetcher(url: str) -> str:
        nonlocal detail_calls
        if "refurbished" in url:
            return catalog
        detail_calls += 1
        return """
        <meta name="description" content="24GB unified memory">
        <script type="application/ld+json">
        {"@type":"Product","name":"Refurbished MacBook Pro"}
        </script>
        """

    rule = WatchRule("memory", ProductCategory.MAC, "MacBook Pro", memory_gb=24)
    cache: dict[str, dict[str, object]] = {}
    adapter = AppleRegionalAdapter(Region.US, (rule,), fetcher=fetcher)
    summaries, _listings, _errors = adapter.observe(cache=cache)
    adapter.observe(cache=cache, previous_catalog_ids={summaries[0].id})
    adapter.observe(cache=cache, previous_catalog_ids=set())
    assert detail_calls == 2


@pytest.mark.parametrize(
    "description",
    [
        "Apple M4 Pro chip, 12-Core CPU, 16-Core GPU, 24GB unified memory, 1TB SSD",
        "Apple M4 Proチップ、12コアCPU、16コアGPU、24GBユニファイドメモリ、1TB SSD",
        "Apple M4 Pro 芯片，配备 12 核中央处理器和 16 核图形处理器，24GB 统一内存，1TB SSD",
        "Apple M4 Pro 晶片配備 12 核心 CPU 及 16 核心 GPU、24GB 統一記憶體、1TB SSD",
    ],
)
def test_parses_localized_mac_detail_fields(description: str) -> None:
    summary = ListingSummary(
        "TEST",
        "MacBook Pro",
        100,
        "https://www.apple.com.cn/shop/product/test",
        ProductCategory.MAC,
        "CNY",
    )
    html = (
        f'<meta name="description" content="{description}">'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"MacBook Pro","url":"/shop/product/test"}'
        "</script>"
    )
    listing = parse_regional_detail(html, summary)
    assert listing.cpu_cores == 12
    assert listing.gpu_cores == 16
    assert listing.memory_gb == 24
    assert listing.storage == "1TB"
    assert listing.url.startswith("https://www.apple.com.cn/")
