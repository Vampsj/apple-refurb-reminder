from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from apple_refurb_reminder.config import ConfigError
from apple_refurb_reminder.models import Region
from apple_refurb_reminder.setup_config import (
    add_rule,
    commit_region_change,
    make_rule,
    migrate_v1,
    read_watch_config,
    remove_rule,
    replace_rule,
    write_watch_config,
)
from apple_refurb_reminder.state import StateError, StateStore, empty_state


def test_migrates_v1_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "subscriptions.yaml"
    original = """
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
    path.write_text(original)
    backup = migrate_v1(path)
    assert backup is not None
    assert backup.read_text() == original
    root = yaml.safe_load(path.read_text())
    assert root["schema_version"] == 2
    assert root["region"] == "JP"
    assert root["rules"][0]["model"] == "MacBook Pro"


def test_migrated_v1_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "subscriptions.yaml"
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
    assert migrate_v1(path) is not None
    assert migrate_v1(path) is None


def test_add_and_remove_rules(tmp_path: Path) -> None:
    path = tmp_path / "watch.yaml"
    first = make_rule(rule_id="mac", category="mac", model="MacBook Pro")
    second = make_rule(
        rule_id="phone",
        category="iphone",
        model="iPhone 16 Pro",
        storage="256GB",
    )
    add_rule(path, Region.US, first)
    add_rule(path, Region.US, second)
    region, rules = read_watch_config(path)
    assert region == Region.US
    assert [rule.id for rule in rules] == ["mac", "phone"]
    remove_rule(path, "phone")
    assert [rule.id for rule in read_watch_config(path)[1]] == ["mac"]


def test_refuses_fourth_rule_and_mixed_region(tmp_path: Path) -> None:
    path = tmp_path / "watch.yaml"
    for index in range(3):
        add_rule(
            path,
            Region.HK,
            make_rule(rule_id=f"rule-{index}", category="ipad", model="iPad Pro"),
        )
    with pytest.raises(ConfigError, match="maximum"):
        add_rule(
            path,
            Region.HK,
            make_rule(rule_id="fourth", category="mac", model="Mac mini"),
        )
    with pytest.raises(ConfigError, match="same region"):
        add_rule(
            path,
            Region.JP,
            make_rule(rule_id="jp", category="mac", model="MacBook Air"),
        )


def test_replaces_rule_atomically(tmp_path: Path) -> None:
    path = tmp_path / "watch.yaml"
    add_rule(path, Region.US, make_rule(rule_id="old", category="mac", model="Mac mini"))
    replace_rule(
        path,
        "old",
        make_rule(rule_id="new", category="iphone", model="iPhone 16"),
    )
    assert [rule.id for rule in read_watch_config(path)[1]] == ["new"]


def test_region_change_archives_rules_and_state(tmp_path: Path) -> None:
    path = tmp_path / "watch.yaml"
    staged = tmp_path / "new.yaml"
    state_path = tmp_path / "data/state.json"
    write_watch_config(
        path,
        Region.JP,
        (make_rule(rule_id="old", category="mac", model="MacBook Pro"),),
    )
    write_watch_config(
        staged,
        Region.HK,
        (make_rule(rule_id="new", category="ipad", model="iPad Pro"),),
    )
    with StateStore(state_path) as store:
        state = empty_state()
        state["listings"]["old:item"] = {"present": True}
        store.save(state)
    archive = commit_region_change(
        path,
        state_path,
        staged,
        now=datetime(2026, 7, 25, tzinfo=UTC),
    )
    assert read_watch_config(path)[0] == Region.HK
    assert read_watch_config(archive / "watch.yaml")[0] == Region.JP
    with StateStore(state_path) as store:
        assert store.load()["listings"] == {}


def test_region_change_refuses_while_monitor_holds_state_lock(tmp_path: Path) -> None:
    path = tmp_path / "watch.yaml"
    staged = tmp_path / "new.yaml"
    state_path = tmp_path / "state.json"
    write_watch_config(
        path,
        Region.JP,
        (make_rule(rule_id="old", category="mac", model="MacBook Pro"),),
    )
    write_watch_config(
        staged,
        Region.US,
        (make_rule(rule_id="new", category="iphone", model="iPhone 16"),),
    )
    with StateStore(state_path), pytest.raises(StateError):
        commit_region_change(path, state_path, staged)
    assert read_watch_config(path)[0] == Region.JP
