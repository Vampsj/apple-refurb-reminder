from pathlib import Path

import pytest

from apple_refurb_reminder.config import ConfigError, load_settings


def write_subscription(path: Path) -> None:
    path.write_text(
        """
schema_version: 1
subscriptions:
  - id: target
    product: MacBook Pro
    display_size_inches: 14
    chip: M5 Pro
    cpu_cores: 15
    gpu_cores: 16
    memory_gb: 48
    storage: 1TB
""".strip()
    )


def test_default_interval_is_ten_minutes(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    value = load_settings(tmp_path / ".env", subscriptions)
    assert value.check_interval_seconds == 600


def test_rejects_too_short_interval(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    env = tmp_path / ".env"
    env.write_text("CHECK_INTERVAL_SECONDS=299")
    with pytest.raises(ConfigError):
        load_settings(env, subscriptions)


def test_rejects_unknown_subscription_field(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    subscriptions.write_text(subscriptions.read_text() + "\n    memroy_gb: 48\n")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / ".env", subscriptions)


def test_loads_schema_v2_with_three_optional_rules(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    config.write_text(
        """
schema_version: 2
region: US
rules:
  - id: macbook
    category: mac
    model: MacBook Pro
    storage: 1TB
  - id: phone
    category: iphone
    model: iPhone 16 Pro
    color: Natural Titanium
  - id: tablet
    category: ipad
    model: iPad Air
""".strip()
    )
    value = load_settings(tmp_path / ".env", config)
    assert value.region == "US"
    assert value.locale == "en-US"
    assert len(value.subscriptions) == 3
    assert value.subscriptions[0].memory_gb is None


def test_rejects_more_than_three_rules(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    rules = "\n".join(
        f"  - id: rule-{index}\n    category: mac\n    model: MacBook Pro"
        for index in range(4)
    )
    config.write_text(f"schema_version: 2\nregion: JP\nrules:\n{rules}\n")
    with pytest.raises(ConfigError, match="between 1 and 3"):
        load_settings(tmp_path / ".env", config)


def test_rejects_env_region_conflict(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    config.write_text(
        "schema_version: 2\nregion: HK\nrules:\n"
        "  - id: ipad\n    category: ipad\n    model: iPad Pro\n"
    )
    env = tmp_path / ".env"
    env.write_text("APPLE_REGION=JP")
    with pytest.raises(ConfigError, match="conflicts"):
        load_settings(env, config)


def test_loads_v2_notification_secrets_from_store(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    env = tmp_path / ".env"
    env.write_text("NOTIFICATION_MODE=discord\n")

    class Store:
        def get(self, key: str) -> str | None:
            return "https://discord.test/secret" if key == "discord_webhook" else None

        def set(self, key: str, value: str) -> None:
            raise AssertionError("load must not write secrets")

    value = load_settings(env, subscriptions, secret_store=Store())
    assert value.discord_webhook == "https://discord.test/secret"


def test_notification_mode_disables_unselected_stale_channel(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    env = tmp_path / ".env"
    env.write_text(
        "NOTIFICATION_MODE=discord\n"
        "SMTP_HOST=smtp.gmail.com\n"
        "SMTP_USERNAME=old@gmail.com\n"
        "EMAIL_FROM=old@gmail.com\n"
        "EMAIL_TO=old@gmail.com\n"
    )

    class Store:
        def get(self, key: str) -> str | None:
            return {
                "discord_webhook": "https://discord.test/current",
                "smtp_password": "stale-password",
            }.get(key)

        def set(self, key: str, value: str) -> None:
            raise AssertionError

    value = load_settings(env, subscriptions, secret_store=Store())
    assert value.discord_webhook is not None
    assert value.email is None
