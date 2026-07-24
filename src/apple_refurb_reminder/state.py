from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class StateError(RuntimeError):
    pass


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_successful_check": None,
        "listings": {},
        "batches": [],
        "incidents": {},
    }


class StateStore(AbstractContextManager["StateStore"]):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self._lock_file: Any = None

    def __enter__(self) -> StateStore:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = self.lock_path.open("a+")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StateError("別の監視プロセスが同じ状態ファイルを使用しています") from exc
        return self

    def __exit__(self, *args: object) -> None:
        if self._lock_file is not None:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_state()
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"状態ファイルを読み込めません: {self.path}") from exc
        if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
            raise StateError("状態ファイルの schema_version が不正です")
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def prune_state(state: dict[str, Any], now: datetime) -> None:
    completed_cutoff = now - timedelta(days=7)
    absent_cutoff = now - timedelta(days=30)
    state["batches"] = [
        batch
        for batch in state["batches"]
        if not (
            all(status in {"sent", "expired"} for status in batch["channels"].values())
            and datetime.fromisoformat(batch["created_at"]) < completed_cutoff
        )
    ]
    for key, record in list(state["listings"].items()):
        if (
            not record.get("present", False)
            and record.get("confirmed_absent_at")
            and datetime.fromisoformat(record["confirmed_absent_at"]) < absent_cutoff
        ):
            del state["listings"][key]


def utc_now() -> datetime:
    return datetime.now(UTC)
