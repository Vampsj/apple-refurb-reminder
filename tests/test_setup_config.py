from pathlib import Path

import pytest
import yaml

from apple_refurb_reminder.config import ConfigError
from apple_refurb_reminder.models import Region
from apple_refurb_reminder.setup_config import (
    add_rule,
    make_rule,
    migrate_v1,
    read_watch_config,
    remove_rule,
)


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
