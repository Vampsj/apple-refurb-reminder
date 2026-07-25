import pytest

from apple_refurb_reminder.notify import render_health_event


@pytest.mark.parametrize(
    ("region", "text"),
    [
        ("US", "3 consecutive"),
        ("JP", "3回連続"),
        ("CN", "连续检查失败 3 次"),
        ("HK", "連續檢查失敗 3 次"),
    ],
)
def test_health_alert_uses_region_language(region: str, text: str) -> None:
    rendered = render_health_event("mac", recovered=False, region=region)
    assert text in rendered.body
