from __future__ import annotations

import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError, _load_subscriptions
from .models import ProductCategory, Region, WatchRule
from .state import StateStore, empty_state


def read_watch_config(path: Path) -> tuple[Region, tuple[WatchRule, ...]]:
    return _load_subscriptions(path)


def write_watch_config(path: Path, region: Region, rules: tuple[WatchRule, ...]) -> None:
    if not 1 <= len(rules) <= 3:
        raise ConfigError("rules must contain between 1 and 3 entries")
    rows: list[dict[str, Any]] = []
    for rule in rules:
        row = asdict(rule)
        row["category"] = rule.category.value
        rows.append({key: value for key, value in row.items() if value is not None})
    content = yaml.safe_dump(
        {"schema_version": 2, "region": region.value, "rules": rows},
        allow_unicode=True,
        sort_keys=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def migrate_v1(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        root = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot parse watch configuration: {exc}") from exc
    if not isinstance(root, dict) or root.get("schema_version") != 1:
        return None
    region, rules = read_watch_config(path)
    backup = path.with_name(f"{path.name}.v1.bak")
    if backup.exists():
        raise ConfigError(f"Migration backup already exists: {backup}")
    shutil.copy2(path, backup)
    try:
        write_watch_config(path, region, rules)
    except Exception:
        shutil.copy2(backup, path)
        raise
    return backup


def add_rule(path: Path, region: Region, rule: WatchRule) -> None:
    if path.exists():
        migrate_v1(path)
        configured_region, rules = read_watch_config(path)
        if configured_region != region:
            raise ConfigError(
                f"This installation uses {configured_region.value}; "
                "all rules must use the same region"
            )
    else:
        rules = ()
    if len(rules) >= 3:
        raise ConfigError("This installation already has the maximum of 3 rules")
    if any(existing.id == rule.id for existing in rules):
        raise ConfigError(f"duplicate rule id: {rule.id}")
    write_watch_config(path, region, (*rules, rule))


def remove_rule(path: Path, rule_id: str) -> None:
    migrate_v1(path)
    region, rules = read_watch_config(path)
    remaining = tuple(rule for rule in rules if rule.id != rule_id)
    if len(remaining) == len(rules):
        raise ConfigError(f"Unknown rule id: {rule_id}")
    if not remaining:
        raise ConfigError("At least one rule is required; add its replacement first")
    write_watch_config(path, region, remaining)


def replace_rule(path: Path, rule_id: str, replacement: WatchRule) -> None:
    migrate_v1(path)
    region, rules = read_watch_config(path)
    if replacement.id != rule_id and any(rule.id == replacement.id for rule in rules):
        raise ConfigError(f"duplicate rule id: {replacement.id}")
    updated = tuple(replacement if rule.id == rule_id else rule for rule in rules)
    if updated == rules:
        raise ConfigError(f"Unknown rule id: {rule_id}")
    write_watch_config(path, region, updated)


def commit_region_change(
    path: Path,
    state_path: Path,
    staged_path: Path,
    *,
    now: datetime | None = None,
) -> Path:
    old_region, _old_rules = read_watch_config(path)
    new_region, _new_rules = read_watch_config(staged_path)
    if old_region == new_region:
        raise ConfigError("The new region must differ from the current region")
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    archive = path.parent / "archive" / f"region-{old_region.value}-{timestamp}"
    with StateStore(state_path) as store:
        store.load()
        archive.mkdir(parents=True, exist_ok=False)
        shutil.copy2(path, archive / path.name)
        if state_path.exists():
            shutil.copy2(state_path, archive / state_path.name)
        staged_path.replace(path)
        store.save(empty_state())
    return archive


def make_rule(
    *,
    rule_id: str,
    category: str,
    model: str,
    storage: str | None = None,
    color: str | None = None,
    display_size_inches: int | None = None,
    chip: str | None = None,
    cpu_cores: int | None = None,
    gpu_cores: int | None = None,
    memory_gb: int | None = None,
    connectivity: str | None = None,
) -> WatchRule:
    try:
        parsed_category = ProductCategory(category.lower())
    except ValueError as exc:
        raise ConfigError("category must be mac, iphone, or ipad") from exc
    return WatchRule(
        id=rule_id.strip(),
        category=parsed_category,
        model=model.strip(),
        display_size_inches=display_size_inches,
        chip=chip,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        memory_gb=memory_gb,
        storage=storage.strip() if storage else None,
        color=color.strip() if color else None,
        connectivity=connectivity.strip() if connectivity else None,
    )
