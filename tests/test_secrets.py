import json
import stat
from pathlib import Path

import pytest

from apple_refurb_reminder.secrets import (
    FileSecretStore,
    SecretStoreError,
    default_secret_store,
)


def test_linux_secret_file_is_created_with_0600_permissions(tmp_path: Path) -> None:
    store = FileSecretStore(tmp_path / "config/secrets.json")
    store.set("discord_webhook", "https://example.test/secret")
    assert store.get("discord_webhook") == "https://example.test/secret"
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert json.loads(store.path.read_text()) == {
        "discord_webhook": "https://example.test/secret"
    }


def test_refuses_insecure_linux_secret_file(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    path.write_text('{"smtp_password": "secret"}')
    path.chmod(0o644)
    with pytest.raises(SecretStoreError, match="0600"):
        FileSecretStore(path).get("smtp_password")


def test_unsupported_platform_is_explicit() -> None:
    with pytest.raises(SecretStoreError, match="not supported"):
        default_secret_store(system="Windows")
