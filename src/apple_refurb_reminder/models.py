from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Subscription:
    id: str
    product: str
    display_size_inches: int
    chip: str
    cpu_cores: int
    gpu_cores: int
    memory_gb: int
    storage: str


@dataclass(frozen=True, slots=True)
class ListingSummary:
    id: str
    title: str
    price_jpy: int
    url: str


@dataclass(frozen=True, slots=True)
class Listing:
    id: str
    title: str
    price_jpy: int
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Listing:
        return cls(**value)


@dataclass(frozen=True, slots=True)
class Match:
    subscription_id: str
    listing: Listing
