from __future__ import annotations

import re

from .models import Listing, Subscription


def _text(value: str | None) -> str | None:
    return re.sub(r"[\s_-]+", "", value).casefold() if value is not None else None


def _storage(value: str | None) -> str | None:
    return re.sub(r"\s+", "", value).upper() if value else None


def missing_required(listing: Listing) -> tuple[str, ...]:
    fields = (
        "product",
        "display_size_inches",
        "chip",
        "cpu_cores",
        "gpu_cores",
        "memory_gb",
        "storage",
    )
    return tuple(field for field in fields if getattr(listing, field) is None)


def matches(subscription: Subscription, listing: Listing) -> bool:
    if missing_required(listing):
        return False
    return all(
        (
            _text(listing.product) == _text(subscription.product),
            listing.display_size_inches == subscription.display_size_inches,
            _text(listing.chip) == _text(subscription.chip),
            listing.cpu_cores == subscription.cpu_cores,
            listing.gpu_cores == subscription.gpu_cores,
            listing.memory_gb == subscription.memory_gb,
            _storage(listing.storage) == _storage(subscription.storage),
        )
    )
