from pathlib import Path

import pytest

from apple_refurb_reminder.setup_notifications import (
    configure_notifications,
    migrate_legacy_secrets,
)


def subscription(path: Path) -> None:
    path.write_text(
        """
schema_version: 2
region: US
rules:
  - id: phone
    category: iphone
    model: iPhone 16 Pro
""".strip()
    )


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def test_discord_is_tested_before_configuration_is_saved(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    subscription(config)
    env = tmp_path / ".env"
    answers = iter(["1"])
    secrets = iter(["https://discord.test/webhook"])
    store = MemorySecrets()
    sent: list[str] = []
    mode = configure_notifications(
        env,
        config,
        input_fn=lambda _prompt: next(answers),
        secret_input=lambda _prompt: next(secrets),
        output=lambda _message: None,
        secret_store=store,
        sender=lambda _settings, selected: sent.append(selected),
    )
    assert mode == "discord"
    assert sent == ["discord"]
    assert store.values["discord_webhook"].endswith("/webhook")
    assert "NOTIFICATION_MODE=discord" in env.read_text()
    assert "discord.test" not in env.read_text()


def test_both_gmail_channels_are_saved_after_test(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    subscription(config)
    env = tmp_path / ".env"
    answers = iter(["3", "1", "person@gmail.com", "alerts@example.com"])
    secret_answers = iter(["discord-secret", "gmail-app-password"])
    store = MemorySecrets()
    configure_notifications(
        env,
        config,
        input_fn=lambda _prompt: next(answers),
        secret_input=lambda _prompt: next(secret_answers),
        output=lambda _message: None,
        secret_store=store,
        sender=lambda settings, mode: (
            None
            if mode == "both" and settings.smtp_host == "smtp.gmail.com"
            else pytest.fail("unexpected candidate settings")
        ),
    )
    assert store.values == {
        "discord_webhook": "discord-secret",
        "smtp_password": "gmail-app-password",
    }
    assert "SMTP_HOST=smtp.gmail.com" in env.read_text()
    assert "gmail-app-password" not in env.read_text()


def test_failed_test_preserves_existing_configuration(tmp_path: Path) -> None:
    config = tmp_path / "watch.yaml"
    subscription(config)
    env = tmp_path / ".env"
    env.write_text("NOTIFICATION_MODE=discord\nLOG_DIR=./logs\n")
    store = MemorySecrets()
    store.values["discord_webhook"] = "old-secret"
    with pytest.raises(RuntimeError, match="delivery failed"):
        configure_notifications(
            env,
            config,
            input_fn=lambda _prompt: "1",
            secret_input=lambda _prompt: "new-secret",
            output=lambda _message: None,
            secret_store=store,
            sender=lambda _settings, _mode: (_ for _ in ()).throw(
                RuntimeError("delivery failed")
            ),
        )
    assert store.values["discord_webhook"] == "old-secret"
    assert env.read_text() == "NOTIFICATION_MODE=discord\nLOG_DIR=./logs\n"


def test_migrates_legacy_plaintext_secrets_out_of_env(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DISCORD_WEBHOOK=https://discord.test/secret\n"
        "SMTP_HOST=smtp.gmail.com\n"
        "SMTP_PASSWORD=app-password\n"
        "EMAIL_TO=person@example.com\n"
    )
    store = MemorySecrets()
    assert migrate_legacy_secrets(env, secret_store=store)
    assert store.values == {
        "discord_webhook": "https://discord.test/secret",
        "smtp_password": "app-password",
    }
    content = env.read_text()
    assert "DISCORD_WEBHOOK" not in content
    assert "SMTP_PASSWORD" not in content
    assert "NOTIFICATION_MODE=both" in content
    assert "SMTP_HOST=smtp.gmail.com" in content
