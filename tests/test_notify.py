from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

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
