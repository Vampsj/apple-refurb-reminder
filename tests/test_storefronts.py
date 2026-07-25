import pytest

from apple_refurb_reminder.models import ProductCategory, Region
from apple_refurb_reminder.storefronts import storefront


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        (Region.JP, "https://www.apple.com/jp/shop/refurbished/mac"),
        (Region.US, "https://www.apple.com/shop/refurbished/iphone"),
        (Region.CN, "https://www.apple.com.cn/shop/refurbished/ipad"),
        (Region.HK, "https://www.apple.com/hk-zh/shop/refurbished/mac"),
    ],
)
def test_catalog_urls(region: Region, expected: str) -> None:
    category = {
        Region.JP: ProductCategory.MAC,
        Region.US: ProductCategory.IPHONE,
        Region.CN: ProductCategory.IPAD,
        Region.HK: ProductCategory.MAC,
    }[region]
    assert storefront(region).catalog_url(category) == expected


def test_region_controls_localization() -> None:
    assert storefront(Region.JP).notification_language == "ja"
    assert storefront(Region.US).currency == "USD"
    assert storefront(Region.CN).notification_language == "zh-CN"
    assert storefront(Region.HK).locale == "zh-HK"
