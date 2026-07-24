from pathlib import Path

from apple_refurb_reminder.apple import AppleJapanAdapter
from apple_refurb_reminder.config import Settings
from apple_refurb_reminder.models import Subscription
from apple_refurb_reminder.service import Monitor
from apple_refurb_reminder.state import empty_state

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = (FIXTURES / "catalog.html").read_text()
DETAIL = (FIXTURES / "detail.html").read_text()
EMPTY_CATALOG = CATALOG.replace(
    '"tiles":[{"title":', '"tiles":[],"unused":[{"title":'
)


def settings(tmp_path: Path) -> Settings:
    return Settings(
        "JP",
        "ja-JP",
        "Asia/Tokyo",
        600,
        tmp_path / "state.json",
        tmp_path / "logs",
        1,
        None,
        None,
        587,
        None,
        None,
        None,
        None,
        True,
        (Subscription("target", "MacBook Pro", 14, "M5 Pro", 15, 16, 48, "1TB"),),
        "test",
    )


def adapter(catalog: str) -> AppleJapanAdapter:
    def fetch(url: str) -> str:
        return catalog if "refurbished" in url else DETAIL

    return AppleJapanAdapter(fetcher=fetch)


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
