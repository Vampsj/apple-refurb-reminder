from __future__ import annotations

from dataclasses import dataclass

from .models import ProductCategory, Region


@dataclass(frozen=True, slots=True)
class Storefront:
    region: Region
    base_url: str
    shop_prefix: str
    locale: str
    timezone: str
    currency: str
    notification_language: str

    def catalog_url(self, category: ProductCategory) -> str:
        return f"{self.base_url}{self.shop_prefix}/shop/refurbished/{category.value}"


STOREFRONTS = {
    Region.JP: Storefront(
        region=Region.JP,
        base_url="https://www.apple.com",
        shop_prefix="/jp",
        locale="ja-JP",
        timezone="Asia/Tokyo",
        currency="JPY",
        notification_language="ja",
    ),
    Region.US: Storefront(
        region=Region.US,
        base_url="https://www.apple.com",
        shop_prefix="",
        locale="en-US",
        timezone="America/Los_Angeles",
        currency="USD",
        notification_language="en",
    ),
    Region.CN: Storefront(
        region=Region.CN,
        base_url="https://www.apple.com.cn",
        shop_prefix="",
        locale="zh-CN",
        timezone="Asia/Shanghai",
        currency="CNY",
        notification_language="zh-CN",
    ),
    Region.HK: Storefront(
        region=Region.HK,
        base_url="https://www.apple.com",
        shop_prefix="/hk-zh",
        locale="zh-HK",
        timezone="Asia/Hong_Kong",
        currency="HKD",
        notification_language="zh-HK",
    ),
}


def storefront(region: Region | str) -> Storefront:
    return STOREFRONTS[Region(str(region).upper())]
