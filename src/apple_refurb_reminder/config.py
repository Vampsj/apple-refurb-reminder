from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import Subscription

ENV_KEYS = {
    "APPLE_REGION",
    "APPLE_LOCALE",
    "DISPLAY_TIMEZONE",
    "CHECK_INTERVAL_SECONDS",
    "STATE_FILE",
    "LOG_DIR",
    "DETAIL_CONCURRENCY",
    "DISCORD_WEBHOOK",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_TO",
    "SMTP_USE_TLS",
}
SUBSCRIPTION_KEYS = {
    "id",
    "product",
    "display_size_inches",
    "chip",
    "cpu_cores",
    "gpu_cores",
    "memory_gb",
    "storage",
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    region: str
    locale: str
    display_timezone: str
    check_interval_seconds: int
    state_file: Path
    log_dir: Path
    detail_concurrency: int
    discord_webhook: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    email_from: str | None
    email_to: str | None
    smtp_use_tls: bool
    subscriptions: tuple[Subscription, ...]
    fingerprint: str


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path}:{number}: KEY=VALUE 形式ではありません")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ENV_KEYS:
            raise ConfigError(f"{path}:{number}: 不明な設定項目: {key}")
        result[key] = value.strip().strip("\"'")
    return result


def _int(values: dict[str, str], key: str, default: int) -> int:
    raw = values.get(key, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} は整数で指定してください") from exc


def _bool(values: dict[str, str], key: str, default: bool) -> bool:
    raw = values.get(key, str(default)).lower()
    if raw not in {"true", "false"}:
        raise ConfigError(f"{key} は true または false で指定してください")
    return raw == "true"


def _load_subscriptions(path: Path) -> tuple[Subscription, ...]:
    if not path.exists():
        raise ConfigError(f"購読設定が見つかりません: {path}")
    try:
        root = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"購読設定を解析できません: {exc}") from exc
    if not isinstance(root, dict) or set(root) != {"schema_version", "subscriptions"}:
        raise ConfigError("購読設定のトップレベル項目は schema_version と subscriptions のみです")
    if root["schema_version"] != 1:
        raise ConfigError("未対応の購読 schema_version です")
    rows = root["subscriptions"]
    if not isinstance(rows, list) or not rows:
        raise ConfigError("subscriptions は1件以上必要です")
    subscriptions: list[Subscription] = []
    ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ConfigError(f"subscriptions[{index}] はオブジェクトで指定してください")
        unknown = set(row) - SUBSCRIPTION_KEYS
        missing = SUBSCRIPTION_KEYS - set(row)
        if unknown or missing:
            raise ConfigError(
                f"subscriptions[{index}] の項目が不正です"
                f" (unknown={sorted(unknown)}, missing={sorted(missing)})"
            )
        subscription = Subscription(**row)
        if subscription.id in ids:
            raise ConfigError(f"購読IDが重複しています: {subscription.id}")
        if subscription.storage.upper().replace(" ", "") not in {
            "256GB",
            "512GB",
            "1TB",
            "2TB",
            "4TB",
            "8TB",
        }:
            raise ConfigError(f"不明なストレージ容量です: {subscription.storage}")
        for name in (
            "display_size_inches",
            "cpu_cores",
            "gpu_cores",
            "memory_gb",
        ):
            if not isinstance(getattr(subscription, name), int) or getattr(subscription, name) <= 0:
                raise ConfigError(f"{subscription.id}.{name} は正の整数で指定してください")
        ids.add(subscription.id)
        subscriptions.append(subscription)
    return tuple(subscriptions)


def load_settings(
    env_path: Path = Path(".env"),
    subscriptions_path: Path = Path("subscriptions.yaml"),
) -> Settings:
    file_values = _read_dotenv(env_path)
    values = {key: os.environ.get(key, value) for key, value in file_values.items()}
    for key in ENV_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
    unknown_apple = [key for key in values if key not in ENV_KEYS]
    if unknown_apple:
        raise ConfigError(f"不明な環境設定: {unknown_apple}")

    interval = _int(values, "CHECK_INTERVAL_SECONDS", 600)
    if interval < 60:
        raise ConfigError("CHECK_INTERVAL_SECONDS は60以上で指定してください")
    concurrency = _int(values, "DETAIL_CONCURRENCY", 3)
    if not 1 <= concurrency <= 10:
        raise ConfigError("DETAIL_CONCURRENCY は1から10で指定してください")
    subscriptions = _load_subscriptions(subscriptions_path)
    discord = values.get("DISCORD_WEBHOOK") or None
    smtp_host = values.get("SMTP_HOST") or None
    email_fields = {
        "SMTP_USERNAME": values.get("SMTP_USERNAME"),
        "SMTP_PASSWORD": values.get("SMTP_PASSWORD"),
        "EMAIL_FROM": values.get("EMAIL_FROM"),
        "EMAIL_TO": values.get("EMAIL_TO"),
    }
    if smtp_host and not all(email_fields.values()):
        raise ConfigError("SMTP を使う場合は認証情報と EMAIL_FROM/EMAIL_TO が必要です")
    public = {
        "region": values.get("APPLE_REGION", "JP"),
        "locale": values.get("APPLE_LOCALE", "ja-JP"),
        "timezone": values.get("DISPLAY_TIMEZONE", "Asia/Tokyo"),
        "interval": interval,
        "state": values.get("STATE_FILE", "./data/state.json"),
        "subscriptions": [subscription.id for subscription in subscriptions],
    }
    fingerprint = hashlib.sha256(
        json.dumps(public, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return Settings(
        region=public["region"],
        locale=public["locale"],
        display_timezone=public["timezone"],
        check_interval_seconds=interval,
        state_file=Path(public["state"]),
        log_dir=Path(values.get("LOG_DIR", "./logs")),
        detail_concurrency=concurrency,
        discord_webhook=discord,
        smtp_host=smtp_host,
        smtp_port=_int(values, "SMTP_PORT", 587),
        smtp_username=email_fields["SMTP_USERNAME"] or None,
        smtp_password=email_fields["SMTP_PASSWORD"] or None,
        email_from=email_fields["EMAIL_FROM"] or None,
        email_to=email_fields["EMAIL_TO"] or None,
        smtp_use_tls=_bool(values, "SMTP_USE_TLS", True),
        subscriptions=subscriptions,
        fingerprint=fingerprint,
    )
