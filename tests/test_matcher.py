from dataclasses import replace

import pytest

from apple_refurb_reminder.matcher import matches, missing_required
from apple_refurb_reminder.models import Listing, Subscription


@pytest.fixture
def subscription() -> Subscription:
    return Subscription("target", "MacBook Pro", 14, "M5 Pro", 15, 16, 48, "1TB")


@pytest.fixture
def listing() -> Listing:
    return Listing(
        "G1MLEJ/A",
        "target",
        455800,
        "https://example.test/product",
        "MacBook Pro",
        14,
        "M5 Pro",
        15,
        16,
        48,
        "1TB",
    )


def test_exact_match(subscription: Subscription, listing: Listing) -> None:
    assert matches(subscription, listing)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("display_size_inches", 16),
        ("cpu_cores", 18),
        ("gpu_cores", 20),
        ("memory_gb", 64),
        ("storage", "2TB"),
    ],
)
def test_rejects_non_exact_variants(
    subscription: Subscription, listing: Listing, field: str, value: object
) -> None:
    assert not matches(subscription, replace(listing, **{field: value}))


def test_missing_attribute_is_unevaluable(
    subscription: Subscription, listing: Listing
) -> None:
    value = replace(listing, memory_gb=None)
    assert missing_required(value) == ("memory_gb",)
    assert not matches(subscription, value)


def test_watch_rule_enforces_connectivity(listing: Listing) -> None:
    from apple_refurb_reminder.models import ProductCategory, WatchRule

    wifi = replace(
        listing,
        category=ProductCategory.IPAD,
        product="iPad Pro",
        connectivity="wifi",
    )
    rule = WatchRule(
        "ipad",
        ProductCategory.IPAD,
        "iPad Pro",
        connectivity="cellular",
    )
    assert not matches(rule, wifi)
