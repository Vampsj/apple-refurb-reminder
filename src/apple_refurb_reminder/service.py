from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .apple import AppleJapanAdapter, AppleRegionalAdapter
from .config import Settings
from .matcher import matches
from .models import Listing, ListingSummary, Match, ProductCategory
from .notify import DiscordChannel, EmailChannel, render_batch, render_health_event
from .state import StateStore, prune_state, utc_now

LOGGER = logging.getLogger(__name__)


class Monitor:
    def __init__(
        self,
        settings: Settings,
        adapter: AppleJapanAdapter | AppleRegionalAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.adapter = adapter or AppleRegionalAdapter(
            settings.region,
            settings.subscriptions,
            detail_concurrency=settings.detail_concurrency,
        )

    def check(
        self,
        state: dict[str, Any],
        *,
        send: bool,
        test_if_empty: bool = False,
    ) -> list[Match]:
        started = time.monotonic()
        state.setdefault("detail_cache", {})
        state.setdefault("catalog_ids", {})
        if isinstance(self.adapter, AppleRegionalAdapter):
            previous_ids = {
                listing_id
                for values in state["catalog_ids"].values()
                for listing_id in values
            }
            summaries, listings, detail_errors = self.adapter.observe(
                cache=state["detail_cache"],
                previous_catalog_ids=previous_ids,
            )
        else:
            summaries, listings, detail_errors = self.adapter.observe()
        summary_ids = {summary.id for summary in summaries}
        listing_by_id = {listing.id: listing for listing in listings}
        now = utc_now()
        new_matches: list[Match] = []
        failed_categories = {
            key.removeprefix("category:")
            for key in detail_errors
            if key.startswith("category:")
        }
        summaries_by_category: dict[str, list[str]] = {}
        for summary in summaries:
            summaries_by_category.setdefault(summary.category.value, []).append(summary.id)
            cache_record = state["detail_cache"].get(summary.id)
            if cache_record is not None:
                cache_record["last_seen_at"] = now.isoformat()
        requested_categories = {
            getattr(rule, "category", ProductCategory.MAC).value
            for rule in self.settings.subscriptions
        }
        for category in requested_categories:
            if category not in failed_categories:
                state["catalog_ids"][category] = summaries_by_category.get(category, [])
        self._update_category_health(
            state,
            requested_categories,
            failed_categories,
            send=send,
        )
        self._update_detail_health(
            state,
            detail_errors,
            listing_by_id,
            summaries,
            send=send,
        )

        for subscription in self.settings.subscriptions:
            subscription_category = getattr(
                subscription, "category", ProductCategory.MAC
            )
            matching_ids: set[str] = set()
            for listing in listings:
                if not matches(subscription, listing):
                    continue
                matching_ids.add(listing.id)
                key = f"{subscription.id}:{listing.id}"
                record = state["listings"].get(key)
                is_appearance = record is None or not record.get("present", False)
                state["listings"][key] = {
                    "subscription_id": subscription.id,
                    "listing_id": listing.id,
                    "listing": listing.to_dict(),
                    "present": True,
                    "misses": 0,
                    "last_seen_at": now.isoformat(),
                    "confirmed_absent_at": None,
                }
                if is_appearance:
                    new_matches.append(Match(subscription.id, listing))

            for _key, record in list(state["listings"].items()):
                if record["subscription_id"] != subscription.id or not record.get("present"):
                    continue
                listing_id = record["listing_id"]
                if listing_id in matching_ids:
                    continue
                if subscription_category.value in failed_categories:
                    continue
                if listing_id in summary_ids and listing_id in listing_by_id:
                    # Present but no longer matches this subscription.
                    record["present"] = False
                    record["misses"] = 2
                    record["confirmed_absent_at"] = now.isoformat()
                elif listing_id not in summary_ids:
                    record["misses"] = int(record.get("misses", 0)) + 1
                    if record["misses"] >= 2:
                        record["present"] = False
                        record["confirmed_absent_at"] = now.isoformat()

        state["last_successful_check"] = now.isoformat()
        if detail_errors:
            LOGGER.warning("詳細を評価できない商品: %s", detail_errors)
        if new_matches:
            batch = self._new_batch(new_matches, now)
            state["batches"].append(batch)
            if send:
                self._deliver(batch, new_matches)
        elif test_if_empty and send:
            self._deliver_test(now)
        prune_state(state, now)
        LOGGER.info(
            "チェック完了 catalog=%d details=%d matched=%d new=%d errors=%d duration=%.2fs",
            len(summaries),
            len(listings),
            sum(
                matches(subscription, listing)
                for subscription in self.settings.subscriptions
                for listing in listings
            ),
            len(new_matches),
            len(detail_errors),
            time.monotonic() - started,
        )
        return new_matches

    def _update_category_health(
        self,
        state: dict[str, Any],
        requested: set[str],
        failed: set[str],
        *,
        send: bool,
    ) -> None:
        incidents = state.setdefault("incidents", {})
        for category in requested:
            record = incidents.setdefault(
                category,
                {"consecutive_failures": 0, "open": False},
            )
            if category in failed:
                record["consecutive_failures"] = (
                    int(record.get("consecutive_failures", 0)) + 1
                )
                if record["consecutive_failures"] >= 3 and not record.get("open"):
                    record["open"] = True
                    if send:
                        self._deliver_health(category, recovered=False)
            else:
                was_open = bool(record.get("open"))
                record["consecutive_failures"] = 0
                record["open"] = False
                if was_open and send:
                    self._deliver_health(category, recovered=True)

    def _deliver_health(self, category: str, *, recovered: bool) -> None:
        rendered = render_health_event(
            category,
            recovered=recovered,
            region=self.settings.region,
        )
        if self.settings.discord_webhook:
            try:
                DiscordChannel(self.settings.discord_webhook).send(rendered)
            except Exception:
                LOGGER.exception("Discord health notification failed")
        if self.settings.smtp_host:
            try:
                EmailChannel(self.settings).send(rendered)
            except Exception:
                LOGGER.exception("Email health notification failed")

    def _update_detail_health(
        self,
        state: dict[str, Any],
        errors: dict[str, str],
        successful: dict[str, Listing],
        summaries: list[ListingSummary],
        *,
        send: bool,
    ) -> None:
        incidents = state.setdefault("incidents", {})
        category_by_id = {summary.id: summary.category.value for summary in summaries}
        detail_errors = {
            listing_id
            for listing_id in errors
            if not listing_id.startswith("category:")
        }
        for listing_id in detail_errors:
            key = f"detail:{listing_id}"
            record = incidents.setdefault(
                key,
                {
                    "consecutive_failures": 0,
                    "open": False,
                    "category": category_by_id.get(listing_id, "product"),
                },
            )
            record["consecutive_failures"] = (
                int(record.get("consecutive_failures", 0)) + 1
            )
            if record["consecutive_failures"] >= 3 and not record.get("open"):
                record["open"] = True
                if send:
                    label = f"{record.get('category', 'product')} / {listing_id}"
                    self._deliver_health(label, recovered=False)
        for key, record in list(incidents.items()):
            if not key.startswith("detail:") or not record.get("open"):
                continue
            listing_id = key.removeprefix("detail:")
            if listing_id in successful:
                record["consecutive_failures"] = 0
                record["open"] = False
                if send:
                    label = f"{record.get('category', 'product')} / {listing_id}"
                    self._deliver_health(label, recovered=True)

    def _new_batch(self, values: list[Match], now: datetime) -> dict[str, Any]:
        channels: dict[str, str] = {}
        if self.settings.discord_webhook:
            channels["discord"] = "pending"
        if self.settings.smtp_host:
            channels["email"] = "pending"
        return {
            "id": f"batch-{int(now.timestamp())}",
            "created_at": now.isoformat(),
            "matches": [
                {"subscription_id": value.subscription_id, "listing": asdict(value.listing)}
                for value in values
            ],
            "channels": channels,
        }

    def _deliver(self, batch_state: dict[str, Any], values: list[Match]) -> None:
        rendered = render_batch(
            values,
            datetime.fromisoformat(batch_state["created_at"]),
            self.settings.display_timezone,
            region=self.settings.region,
        )
        if batch_state["channels"].get("discord") == "pending":
            try:
                DiscordChannel(self.settings.discord_webhook or "").send(rendered)
                batch_state["channels"]["discord"] = "sent"
            except Exception:
                LOGGER.exception("Discord 通知に失敗しました")
        if batch_state["channels"].get("email") == "pending":
            try:
                EmailChannel(self.settings).send(rendered)
                batch_state["channels"]["email"] = "sent"
            except Exception:
                LOGGER.exception("Email 通知に失敗しました")

    def _deliver_test(self, now: datetime) -> None:
        rendered = render_batch(
            [],
            now,
            self.settings.display_timezone,
            test=True,
            region=self.settings.region,
        )
        if self.settings.discord_webhook:
            DiscordChannel(self.settings.discord_webhook).send(rendered)
        if self.settings.smtp_host:
            EmailChannel(self.settings).send(rendered)

    def retry_pending(self, state: dict[str, Any]) -> None:
        for batch in state["batches"]:
            if not any(value == "pending" for value in batch["channels"].values()):
                continue
            values = [
                Match(row["subscription_id"], Listing.from_dict(row["listing"]))
                for row in batch["matches"]
                if state["listings"].get(
                    f"{row['subscription_id']}:{row['listing']['id']}", {}
                ).get("present", False)
            ]
            if not values:
                for channel, status in batch["channels"].items():
                    if status == "pending":
                        batch["channels"][channel] = "expired"
                continue
            self._deliver(batch, values)


def run_forever(settings: Settings) -> None:
    monitor = Monitor(settings)
    with StateStore(settings.state_file) as store:
        state = store.load()
        while True:
            try:
                monitor.retry_pending(state)
                monitor.check(state, send=True)
                store.save(state)
            except KeyboardInterrupt:
                store.save(state)
                return
            except Exception:
                LOGGER.exception("監視チェックに失敗しました")
                store.save(state)
            time.sleep(settings.check_interval_seconds)
