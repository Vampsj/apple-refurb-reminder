from dataclasses import replace
from pathlib import Path

from apple_refurb_reminder.apple import AppleRegionalAdapter
from apple_refurb_reminder.config import Settings
from apple_refurb_reminder.models import ProductCategory, Subscription, WatchRule
from apple_refurb_reminder.notify import PermanentDeliveryError, RenderedBatch
from apple_refurb_reminder.service import Monitor
from apple_refurb_reminder.state import empty_state

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = (FIXTURES / "catalog.html").read_text()
DETAIL = (FIXTURES / "detail.html").read_text()


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


def adapter() -> AppleRegionalAdapter:
    def fetch(url: str) -> str:
        return CATALOG if "refurbished" in url else DETAIL

    return AppleRegionalAdapter(
        "JP",
        (WatchRule("target", ProductCategory.MAC, "MacBook Pro"),),
        fetcher=fetch,
    )


def test_permanent_channel_failure_is_suspended_and_reported_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = replace(
        settings(tmp_path),
        discord_webhook="https://discord.test/webhook",
    )
    monitor = Monitor(configured, adapter())
    state = empty_state()
    monitor._reconcile_notification_config(state, send=False)
    reports: list[str] = []

    def fail(_self, _rendered):
        raise PermanentDeliveryError("invalid webhook")

    monkeypatch.setattr("apple_refurb_reminder.service.DiscordChannel.send", fail)
    monkeypatch.setattr(
        monitor,
        "_open_channel_incident",
        lambda channel: reports.append(channel),
    )
    statuses = {"discord": "pending"}
    rendered = RenderedBatch("subject", "body", ("body",))
    monitor._send_channel("discord", rendered, statuses)

    assert statuses == {"discord": "suspended"}
    assert reports == ["discord"]


def test_config_change_reactivates_suspended_batches(tmp_path: Path) -> None:
    monitor = Monitor(settings(tmp_path), adapter())
    state = empty_state()
    state["notification_config_fingerprint"] = "old"
    state["incidents"]["channel:discord"] = {"open": True}
    state["batches"].append(
        {
            "id": "batch",
            "created_at": "2026-07-24T00:00:00+00:00",
            "matches": [],
            "channels": {"discord": "suspended"},
        }
    )
    events: list[tuple[str, bool]] = []
    monitor._deliver_health = lambda category, recovered: events.append(
        (category, recovered)
    )

    monitor._reconcile_notification_config(state, send=True)

    assert state["incidents"]["channel:discord"]["open"] is False
    assert state["batches"][0]["channels"]["discord"] == "pending"
    assert events == [("discord notification channel", True)]


def test_new_batches_do_not_retry_a_suspended_channel(tmp_path: Path) -> None:
    configured = replace(
        settings(tmp_path),
        discord_webhook="https://discord.test/webhook",
    )
    monitor = Monitor(configured, adapter())
    state = empty_state()
    state["incidents"]["channel:discord"] = {"open": True}
    monitor._reconcile_notification_config(state, send=False)

    monitor.check(state, send=False)

    assert state["batches"][0]["channels"]["discord"] == "suspended"
