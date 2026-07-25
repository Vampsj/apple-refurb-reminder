from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class MacOSKeychainStore:
    service = "com.apple-refurb-reminder"

    def get(self, key: str) -> str | None:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                key,
                "-s",
                self.service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 44:
            return None
        if result.returncode != 0:
            raise SecretStoreError("Could not read a secret from macOS Keychain")
        return result.stdout.rstrip("\n")

    def set(self, key: str, value: str) -> None:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-a",
                key,
                "-s",
                self.service,
                "-w",
                value,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SecretStoreError("Could not save a secret to macOS Keychain")


class FileSecretStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        if self.path.stat().st_mode & 0o077:
            raise SecretStoreError(f"Secret file permissions must be 0600: {self.path}")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SecretStoreError(f"Could not read secret file: {self.path}") from exc
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(secret, str)
            for key, secret in value.items()
        ):
            raise SecretStoreError(f"Invalid secret file: {self.path}")
        return value

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        values = self._read()
        values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".secrets.", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(values, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def default_secret_store(
    *,
    system: str | None = None,
    home: Path | None = None,
) -> SecretStore:
    operating_system = system or platform.system()
    if operating_system == "Darwin":
        return MacOSKeychainStore()
    if operating_system == "Linux":
        root = home or Path.home()
        return FileSecretStore(root / ".config/apple-refurb-reminder/secrets.json")
    raise SecretStoreError(
        f"{operating_system} is not supported. V1 supports macOS; Linux is experimental."
    )
