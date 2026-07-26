from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .config import ConfigError, Settings, load_settings
from .logging_setup import configure_logging
from .models import Region
from .notify import DiscordChannel, EmailChannel, render_batch
from .service import Monitor, run_forever
from .setup_config import (
    add_rule,
    commit_region_change,
    make_rule,
    read_watch_config,
    remove_rule,
    replace_rule,
    write_watch_config,
)
from .setup_notifications import configure_notifications, write_env_settings
from .setup_wizard import interactive_add_rule
from .state import StateError, StateStore, empty_state, utc_now
from .storefronts import storefront


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apple-refurb-reminder")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--subscriptions", type=Path, default=Path("subscriptions.yaml"))
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config")
    check = sub.add_parser("check-once")
    check.add_argument("--send", action="store_true")
    check.add_argument("--send-test-if-empty", action="store_true")
    sub.add_parser("test-notifications")
    sub.add_parser("run")
    sub.add_parser("status")
    reset = sub.add_parser("reset-state")
    reset.add_argument("--yes", action="store_true")
    setup = sub.add_parser("setup", help="Manage watch rules and notification settings")
    setup_sub = setup.add_subparsers(dest="setup_command")
    setup_sub.add_parser("list", help="List the configured region and watch rules")
    add = setup_sub.add_parser("add", help="Add a watch rule (maximum: 3)")
    add.add_argument("--region", choices=[value.value for value in Region])
    add.add_argument("--id")
    add.add_argument("--category", choices=["mac", "iphone", "ipad"])
    add.add_argument("--model")
    add.add_argument("--storage")
    add.add_argument("--color")
    remove = setup_sub.add_parser("remove", help="Remove a watch rule")
    remove.add_argument("rule_id")
    edit = setup_sub.add_parser("edit", help="Replace an existing watch rule")
    edit.add_argument("rule_id")
    region = setup_sub.add_parser("region", help="Change region and rebuild rules")
    region.add_argument("new_region", choices=[value.value for value in Region])
    setup_sub.add_parser(
        "notifications",
        help="Configure and test Discord, Email, or both",
    )
    return parser


def _load(args: argparse.Namespace) -> Settings:
    return load_settings(args.env, args.subscriptions)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "setup":
            if args.setup_command is None:
                interactive_add_rule(args.subscriptions)
                return 0
            if args.setup_command == "list":
                region, rules = read_watch_config(args.subscriptions)
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
                return 0
            if args.setup_command == "add":
                if not all((args.region, args.id, args.category, args.model)):
                    interactive_add_rule(args.subscriptions)
                    return 0
                region = args.region or input("Region [JP/US/CN/HK]: ").strip().upper()
                rule_id = args.id or input("Rule ID: ").strip()
                category = args.category or input("Category [mac/iphone/ipad]: ").strip()
                model = args.model or input("Exact model name: ").strip()
                rule = make_rule(
                    rule_id=rule_id,
                    category=category,
                    model=model,
                    storage=args.storage,
                    color=args.color,
                )
                add_rule(args.subscriptions, Region(region), rule)
                print(f"Added rule {rule.id}. Current matching stock will notify immediately.")
                return 0
            if args.setup_command == "remove":
                remove_rule(args.subscriptions, args.rule_id)
                print(f"Removed rule {args.rule_id}.")
                return 0
            if args.setup_command == "edit":
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
            if args.setup_command == "region":
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
                    settings = _load(args)
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
            if args.setup_command == "notifications":
                configure_notifications(args.env, args.subscriptions)
                return 0
        settings = _load(args)
        configure_logging(settings.log_dir, args.verbose)
        if args.command == "validate-config":
            print(f"設定は有効です (fingerprint={settings.fingerprint})")
            return 0
        if args.command == "test-notifications":
            rendered = render_batch(
                [],
                utc_now(),
                settings.display_timezone,
                test=True,
                region=settings.region,
            )
            if settings.discord_webhook:
                DiscordChannel(settings.discord_webhook).send(rendered)
            if settings.smtp_host:
                EmailChannel(settings).send(rendered)
            if not settings.discord_webhook and not settings.smtp_host:
                raise ConfigError("通知チャネルが設定されていません")
            print("TEST 通知を送信しました")
            return 0
        if args.command == "run":
            run_forever(settings)
            return 0
        if args.command == "reset-state":
            if not args.yes:
                answer = input("状態をリセットしますか？ [y/N] ")
                if answer.lower() != "y":
                    print("キャンセルしました")
                    return 1
            with StateStore(settings.state_file) as store:
                store.save(empty_state())
            print("状態をリセットしました")
            return 0
        if args.command == "status":
            with StateStore(settings.state_file) as store:
                state = store.load()
            output = {
                "config_fingerprint": settings.fingerprint,
                "last_successful_check": state["last_successful_check"],
                "present_matches": sum(
                    record.get("present", False) for record in state["listings"].values()
                ),
                "pending_deliveries": sum(
                    status == "pending"
                    for batch in state["batches"]
                    for status in batch["channels"].values()
                ),
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        if args.command == "check-once":
            state = empty_state()
            results = Monitor(settings).check(
                state,
                send=args.send or args.send_test_if_empty,
                test_if_empty=args.send_test_if_empty,
            )
            print(
                json.dumps(
                    [
                        {
                            "subscription_id": value.subscription_id,
                            "listing": value.listing.to_dict(),
                        }
                        for value in results
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
    except (ConfigError, StateError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"実行に失敗しました: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
