from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from .config import ConfigError, load_settings
from .models import Region
from .setup_config import (
    add_rule,
    commit_region_change,
    make_rule,
    migrate_v1,
    read_watch_config,
    remove_rule,
    replace_rule,
    write_watch_config,
)
from .setup_notifications import (
    configure_notifications,
    migrate_legacy_secrets,
    write_env_settings,
)
from .setup_wizard import interactive_add_rule
from .storefronts import storefront


def handle_setup(args: argparse.Namespace) -> int:
    if args.setup_command is None:
        interactive_add_rule(args.subscriptions)
        return 0
    if args.setup_command == "list":
        _list_rules(args.subscriptions)
        return 0
    if args.setup_command == "add":
        return _add(args)
    if args.setup_command == "remove":
        remove_rule(args.subscriptions, args.rule_id)
        print(f"Removed rule {args.rule_id}.")
        return 0
    if args.setup_command == "edit":
        return _edit(args)
    if args.setup_command == "region":
        return _change_region(args)
    if args.setup_command == "notifications":
        configure_notifications(args.env, args.subscriptions)
        return 0
    if args.setup_command == "migrate":
        return _migrate(args)
    raise ConfigError(f"Unknown setup command: {args.setup_command}")


def _list_rules(path: Path) -> None:
    region, rules = read_watch_config(path)
    print(f"Region: {region.value}")
    for rule in rules:
        criteria = [
            f"{key}={value}"
            for key, value in (
                ("storage", rule.storage),
                ("color", rule.color),
            )
            if value is not None
        ]
        suffix = f" ({', '.join(criteria)})" if criteria else " (Any configuration)"
        print(f"- {rule.id}: {rule.category.value} / {rule.model}{suffix}")


def _add(args: argparse.Namespace) -> int:
    if not all((args.region, args.id, args.category, args.model)):
        interactive_add_rule(args.subscriptions)
        return 0
    rule = make_rule(
        rule_id=args.id,
        category=args.category,
        model=args.model,
        storage=args.storage,
        color=args.color,
    )
    add_rule(args.subscriptions, Region(args.region), rule)
    print(f"Added rule {rule.id}. Current matching stock will notify immediately.")
    return 0


def _edit(args: argparse.Namespace) -> int:
    region, rules = read_watch_config(args.subscriptions)
    if not any(rule.id == args.rule_id for rule in rules):
        raise ConfigError(f"Unknown rule id: {args.rule_id}")
    replacement = interactive_add_rule(
        args.subscriptions,
        region_override=region,
        save=False,
    )
    replace_rule(args.subscriptions, args.rule_id, replacement)
    print(f"Replaced rule {args.rule_id} with {replacement.id}.")
    return 0


def _change_region(args: argparse.Namespace) -> int:
    current, _rules = read_watch_config(args.subscriptions)
    new_region = Region(args.new_region)
    if current == new_region:
        raise ConfigError(f"This installation already uses {current.value}")
    confirmation = input(
        f"Type {new_region.value} to archive {current.value} rules and state: "
    )
    if confirmation != new_region.value:
        print("Region change cancelled.")
        return 1
    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory) / args.subscriptions.name
        rule = interactive_add_rule(
            staged,
            region_override=new_region,
            save=False,
        )
        write_watch_config(staged, new_region, (rule,))
        settings = load_settings(args.env, args.subscriptions)
        archive = commit_region_change(
            args.subscriptions,
            settings.state_file,
            staged,
        )
        store = storefront(new_region)
        write_env_settings(
            args.env,
            {
                "APPLE_REGION": new_region.value,
                "APPLE_LOCALE": store.locale,
                "DISPLAY_TIMEZONE": store.timezone,
            },
        )
    print(f"Region changed to {new_region.value}. Archive: {archive}")
    return 0


def _migrate(args: argparse.Namespace) -> int:
    backup = migrate_v1(args.subscriptions)
    secrets_migrated = migrate_legacy_secrets(args.env)
    if backup:
        print(f"Migrated watch configuration. Backup: {backup}")
    else:
        print("Watch configuration is already current.")
    if secrets_migrated:
        print("Moved legacy notification secrets to the platform secret store.")
    return 0
