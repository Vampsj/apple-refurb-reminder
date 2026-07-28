from datetime import timedelta
from pathlib import Path

from apple_refurb_reminder.apple import AppleRegionalAdapter
from apple_refurb_reminder.config import Settings
from apple_refurb_reminder.models import ProductCategory, Subscription, WatchRule
from apple_refurb_reminder.service import Monitor
from apple_refurb_reminder.state import empty_state, prune_state, utc_now

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = (FIXTURES / "catalog.html").read_text()
DETAIL = (FIXTURES / "detail.html").read_text()
EMPTY_CATALOG = CATALOG.replace(
    '"tiles":[{"title":', '"tiles":[],"unused":[{"title":'
)


def settings(tmp_path: Path) -> Settings:
    return Settings(
        region="JP",
        locale="ja-JP",
        display_timezone="Asia/Tokyo",
        check_interval_seconds=600,
        state_file=tmp_path / "state.json",
        log_dir=tmp_path / "logs",
        detail_concurrency=1,
        notification_mode=None,
        discord_webhook=None,
        email=None,
        subscriptions=(
            Subscription("target", "MacBook Pro", 14, "M5 Pro", 15, 16, 48, "1TB"),
        ),
        fingerprint="test",
    )


def adapter(catalog: str) -> AppleRegionalAdapter:
    def fetch(url: str) -> str:
        return catalog if "refurbished" in url else DETAIL

    return AppleRegionalAdapter(
        "JP",
        (
            WatchRule(
                "target",
                ProductCategory.MAC,
                "MacBook Pro",
                display_size_inches=14,
                chip="M5 Pro",
                cpu_cores=15,
                gpu_cores=16,
                memory_gb=48,
                storage="1TB",
            ),
        ),
        fetcher=fetch,
    )


def test_first_seen_then_continuous_does_not_repeat(tmp_path: Path) -> None:
    state = empty_state()
    monitor = Monitor(settings(tmp_path), adapter(CATALOG))
    assert len(monitor.check(state, send=False)) == 1
    assert monitor.check(state, send=False) == []


def test_requires_two_absences_before_reappearance(tmp_path: Path) -> None:
    state = empty_state()
    target_settings = settings(tmp_path)
    Monitor(target_settings, adapter(CATALOG)).check(state, send=False)
    Monitor(target_settings, adapter(EMPTY_CATALOG)).check(state, send=False)
    assert Monitor(target_settings, adapter(CATALOG)).check(state, send=False) == []
    Monitor(target_settings, adapter(EMPTY_CATALOG)).check(state, send=False)
    Monitor(target_settings, adapter(EMPTY_CATALOG)).check(state, send=False)
    assert len(Monitor(target_settings, adapter(CATALOG)).check(state, send=False)) == 1


def test_category_failure_does_not_increment_absence(tmp_path: Path) -> None:
    state = empty_state()
    target_settings = settings(tmp_path)
    Monitor(target_settings, adapter(CATALOG)).check(state, send=False)

    class FailedMacAdapter:
        def observe(self):
            return [], [], {"category:mac": "timed out"}

    Monitor(target_settings, FailedMacAdapter()).check(state, send=False)
    record = next(iter(state["listings"].values()))
    assert record["present"] is True
    assert record["misses"] == 0


def test_old_detail_cache_is_pruned() -> None:
    now = utc_now()
    state = empty_state()
    state["detail_cache"] = {
        "old": {"last_seen_at": (now - timedelta(days=31)).isoformat()},
        "current": {"last_seen_at": now.isoformat()},
    }
    prune_state(state, now)
    assert set(state["detail_cache"]) == {"current"}


def test_category_incident_opens_after_three_failures_and_recovers(
    tmp_path: Path,
) -> None:
    state = empty_state()
    monitor = Monitor(settings(tmp_path), adapter(CATALOG))
    events: list[tuple[str, bool]] = []
    monitor._deliver_health = lambda category, recovered: events.append(
        (category, recovered)
    )

    class FailedMacAdapter:
        def observe(self):
            return [], [], {"category:mac": "timed out"}

    monitor.adapter = FailedMacAdapter()
    monitor.check(state, send=True)
    monitor.check(state, send=True)
    assert events == []
    monitor.check(state, send=True)
    monitor.check(state, send=True)
    assert events == [("mac", False)]
    monitor.adapter = adapter(CATALOG)
    monitor.check(state, send=True)
    assert events == [("mac", False), ("mac", True)]


def test_detail_incident_opens_after_three_failures_and_recovers(
    tmp_path: Path,
) -> None:
    state = empty_state()
    target_settings = settings(tmp_path)
    summary, listing, _errors = adapter(CATALOG).observe()
    product_id = summary[0].id

    class DetailAdapter:
        failing = True

        def observe(self):
            if self.failing:
                return summary, [], {product_id: "Product JSON-LD missing"}
            return summary, listing, {}

    detail_adapter = DetailAdapter()
    monitor = Monitor(target_settings, detail_adapter)
    events: list[tuple[str, bool]] = []
    monitor._deliver_health = lambda category, recovered: events.append(
        (category, recovered)
    )
    monitor.check(state, send=True)
    monitor.check(state, send=True)
    monitor.check(state, send=True)
    assert events == [(f"mac / {product_id}", False)]
    detail_adapter.failing = False
    monitor.check(state, send=True)
    assert events == [
        (f"mac / {product_id}", False),
        (f"mac / {product_id}", True),
    ]


def test_bulk_detail_incident_opens_immediately_and_recovers(tmp_path: Path) -> None:
    state = empty_state()
    monitor = Monitor(settings(tmp_path), adapter(CATALOG))
    events: list[tuple[str, bool]] = []
    monitor._deliver_health = lambda category, recovered: events.append(
        (category, recovered)
    )
    summaries, listings, _errors = adapter(CATALOG).observe()
    failures = {
        f"failed-{number}": "Product JSON-LD missing" for number in range(3)
    }

    class BulkFailureAdapter:
        failing = True

        def observe(self):
            if self.failing:
                return summaries, listings[:2], failures
            return summaries, listings, {}

    bulk_adapter = BulkFailureAdapter()
    monitor.adapter = bulk_adapter
    monitor.check(state, send=True)
    monitor.check(state, send=True)
    assert events == [("bulk detail parsing", False)]
    bulk_adapter.failing = False
    monitor.check(state, send=True)
    assert events == [
        ("bulk detail parsing", False),
        ("bulk detail parsing", True),
    ]
