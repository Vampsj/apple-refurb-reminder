from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Region(StrEnum):
    JP = "JP"
    US = "US"
    CN = "CN"
    HK = "HK"


class ProductCategory(StrEnum):
    MAC = "mac"
    IPHONE = "iphone"
    IPAD = "ipad"


class NotificationMode(StrEnum):
    DISCORD = "discord"
    EMAIL = "email"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class WatchRule:
    id: str
    category: ProductCategory
    model: str
    display_size_inches: int | None = None
    chip: str | None = None
    cpu_cores: int | None = None
    gpu_cores: int | None = None
    memory_gb: int | None = None
    storage: str | None = None
    color: str | None = None
    connectivity: str | None = None


@dataclass(frozen=True, slots=True)
class Subscription:
    """Legacy schema-v1 rule kept for migration and API compatibility."""

    id: str
    product: str
    display_size_inches: int
    chip: str
    cpu_cores: int
    gpu_cores: int
    memory_gb: int
    storage: str

    def to_watch_rule(self) -> WatchRule:
        return WatchRule(
            id=self.id,
            category=ProductCategory.MAC,
            model=self.product,
            display_size_inches=self.display_size_inches,
            chip=self.chip,
            cpu_cores=self.cpu_cores,
            gpu_cores=self.gpu_cores,
            memory_gb=self.memory_gb,
            storage=self.storage,
        )


@dataclass(frozen=True, slots=True)
class ListingSummary:
    id: str
    title: str
    price_amount: int
    url: str
    category: ProductCategory = ProductCategory.MAC
    currency: str = "JPY"
    dimensions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Listing:
    id: str
    title: str
    price_amount: int
    url: str
    product: str | None
    display_size_inches: int | None
    chip: str | None
    cpu_cores: int | None
    gpu_cores: int | None
    memory_gb: int | None
    storage: str | None
    color: str | None = None
    keyboard: str | None = None
    connectivity: str | None = None
    category: ProductCategory = ProductCategory.MAC
    currency: str = "JPY"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Listing:
        normalized = dict(value)
        if "price_amount" not in normalized and "price_jpy" in normalized:
            normalized["price_amount"] = normalized.pop("price_jpy")
        normalized["category"] = ProductCategory(
            normalized.get("category", ProductCategory.MAC)
        )
        return cls(**normalized)


@dataclass(frozen=True, slots=True)
class Match:
    subscription_id: str
    listing: Listing
