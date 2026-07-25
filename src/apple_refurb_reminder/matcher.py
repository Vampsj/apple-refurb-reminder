from __future__ import annotations

import re

from .models import Listing, Subscription, WatchRule


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


def matches(subscription: Subscription | WatchRule, listing: Listing) -> bool:
    if isinstance(subscription, Subscription):
        subscription = subscription.to_watch_rule()
    if listing.category != subscription.category:
        return False
    comparisons = {
        "model": (_text(listing.product), _text(subscription.model)),
        "display_size_inches": (
            listing.display_size_inches,
            subscription.display_size_inches,
        ),
        "chip": (_text(listing.chip), _text(subscription.chip)),
        "cpu_cores": (listing.cpu_cores, subscription.cpu_cores),
        "gpu_cores": (listing.gpu_cores, subscription.gpu_cores),
        "memory_gb": (listing.memory_gb, subscription.memory_gb),
        "storage": (_storage(listing.storage), _storage(subscription.storage)),
        "color": (_text(listing.color), _text(subscription.color)),
    }
    for actual, expected in comparisons.values():
        if expected is None:
            continue
        if actual is None or actual != expected:
            return False
    return True
