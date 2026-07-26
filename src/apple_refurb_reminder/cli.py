from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, Settings, load_settings
from .logging_setup import configure_logging
from .models import Region
from .notify import DiscordChannel, EmailChannel, render_batch
from .service import Monitor, run_forever
from .setup_cli import handle_setup
from .state import StateError, StateStore, empty_state, utc_now


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
    setup_sub.add_parser("migrate", help="Migrate a schema-v1 watch file to schema v2")
    return parser


def _load(args: argparse.Namespace) -> Settings:
    return load_settings(args.env, args.subscriptions)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "setup":
            return handle_setup(args)
        settings = _load(args)
        configure_logging(settings.log_dir, args.verbose)
        if args.command == "validate-config":
            print(f"Configuration is valid (fingerprint={settings.fingerprint})")
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
            if settings.email:
                EmailChannel(settings).send(rendered)
            if not settings.discord_webhook and not settings.email:
                raise ConfigError("通知チャネルが設定されていません")
            print("TEST notification sent.")
            return 0
        if args.command == "run":
            run_forever(settings)
            return 0
        if args.command == "reset-state":
            if not args.yes:
                answer = input("Reset all monitor state? [y/N] ")
                if answer.lower() != "y":
                    print("Cancelled.")
                    return 1
            with StateStore(settings.state_file) as store:
                store.save(empty_state())
            print("Monitor state reset.")
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
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Execution failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
