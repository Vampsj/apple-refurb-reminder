from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

from apple_refurb_reminder.models import Listing, Match, ProductCategory
from apple_refurb_reminder.notify import DiscordChannel, render_batch


class Response:
    status = 204

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_discord_request_has_explicit_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    def cloudflare_guard(request: object, timeout: int) -> Response:
        assert timeout == 20
        user_agent = request.get_header("User-agent")
        if not user_agent:
            raise HTTPError(
                request.full_url,
                403,
                "Cloudflare error code 1010",
                {},
                None,
            )
        return Response()

    monkeypatch.setattr("apple_refurb_reminder.notify.urlopen", cloudflare_guard)
    batch = render_batch(
        [],
        datetime(2026, 7, 24, tzinfo=UTC),
        "Asia/Tokyo",
        test=True,
    )
    DiscordChannel("https://discord.com/api/webhooks/id/token").send(batch)


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ("US", "TEST (no matching inventory today)"),
        ("JP", "TEST（本日は一致する実在庫なし）"),
        ("CN", "TEST（今日无匹配库存）"),
        ("HK", "TEST（今日無符合條件的庫存）"),
    ],
)
def test_empty_test_title_and_body_follow_region(region: str, expected: str) -> None:
    batch = render_batch(
        [],
        datetime(2026, 7, 24, tzinfo=UTC),
        "UTC",
        test=True,
        region=region,
    )
    assert batch.subject == expected
    assert batch.body == expected


def test_stock_notification_uses_region_labels_and_currency() -> None:
    listing = Listing(
        "id",
        "Refurbished iPhone 16 Pro 256GB",
        799,
        "https://www.apple.com/shop/product/id",
        "iPhone 16 Pro",
        None,
        None,
        None,
        None,
        None,
        "256GB",
        category=ProductCategory.IPHONE,
        currency="USD",
    )
    batch = render_batch(
        [Match("phone", listing)],
        datetime(2026, 7, 24, tzinfo=UTC),
        "UTC",
        region="US",
    )
    assert "Price: $799" in batch.body
    assert "Rules: phone" in batch.body
    assert "None" not in batch.body
