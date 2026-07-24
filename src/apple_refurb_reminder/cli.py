from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, Settings, load_settings
from .logging_setup import configure_logging
from .notify import DiscordChannel, EmailChannel, render_batch
from .service import Monitor, run_forever
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
    return parser


def _load(args: argparse.Namespace) -> Settings:
    return load_settings(args.env, args.subscriptions)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = _load(args)
        configure_logging(settings.log_dir, args.verbose)
        if args.command == "validate-config":
            print(f"設定は有効です (fingerprint={settings.fingerprint})")
            return 0
        if args.command == "test-notifications":
            rendered = render_batch([], utc_now(), settings.display_timezone, test=True)
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
