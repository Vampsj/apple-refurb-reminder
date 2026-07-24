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
    env.write_text("CHECK_INTERVAL_SECONDS=59")
    with pytest.raises(ConfigError):
        load_settings(env, subscriptions)


def test_rejects_unknown_subscription_field(tmp_path: Path) -> None:
    subscriptions = tmp_path / "subscriptions.yaml"
    write_subscription(subscriptions)
    subscriptions.write_text(subscriptions.read_text() + "\n    memroy_gb: 48\n")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / ".env", subscriptions)
