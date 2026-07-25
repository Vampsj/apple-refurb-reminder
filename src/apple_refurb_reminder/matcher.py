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


def could_match(rule: WatchRule, listing: Listing) -> bool:
    """Return true when known catalog fields do not disqualify the listing."""
    if listing.category != rule.category:
        return False
    comparisons = (
        (_text(listing.product), _text(rule.model)),
        (listing.display_size_inches, rule.display_size_inches),
        (_text(listing.chip), _text(rule.chip)),
        (listing.cpu_cores, rule.cpu_cores),
        (listing.gpu_cores, rule.gpu_cores),
        (listing.memory_gb, rule.memory_gb),
        (_storage(listing.storage), _storage(rule.storage)),
        (_text(listing.color), _text(rule.color)),
        (_text(listing.connectivity), _text(rule.connectivity)),
    )
    return all(
        expected is None or actual is None or actual == expected
        for actual, expected in comparisons
    )


def needs_detail(rule: WatchRule, listing: Listing) -> bool:
    if not could_match(rule, listing):
        return False
    comparisons = (
        (listing.product, rule.model),
        (listing.display_size_inches, rule.display_size_inches),
        (listing.chip, rule.chip),
        (listing.cpu_cores, rule.cpu_cores),
        (listing.gpu_cores, rule.gpu_cores),
        (listing.memory_gb, rule.memory_gb),
        (listing.storage, rule.storage),
        (listing.color, rule.color),
        (listing.connectivity, rule.connectivity),
    )
    return any(expected is not None and actual is None for actual, expected in comparisons)
