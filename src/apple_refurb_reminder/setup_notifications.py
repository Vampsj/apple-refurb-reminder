from __future__ import annotations

import getpass
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .config import Settings, load_settings
from .notify import DiscordChannel, EmailChannel, render_batch
from .secrets import SecretStore, default_secret_store
from .state import utc_now

Input = Callable[[str], str]
SecretInput = Callable[[str], str]
Output = Callable[[str], None]


def _required(prompt: str, reader: Input | SecretInput) -> str:
    while True:
        value = reader(f"{prompt}: ").strip()
        if value:
            return value


def _numbered_choice(
    prompt: str,
    choices: tuple[str, ...],
    input_fn: Input,
    output: Output,
) -> str:
    for index, choice in enumerate(choices, 1):
        output(f"  {index}. {choice}")
    while True:
        value = input_fn(f"{prompt} [1-{len(choices)}]: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value) - 1]
        output("Please enter one of the displayed numbers.")


def write_env_settings(path: Path, updates: dict[str, str]) -> None:
    secret_keys = {"DISCORD_WEBHOOK", "SMTP_PASSWORD"}
    existing: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    written: set[str] = set()
    for line in existing:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in secret_keys:
            continue
        if key in updates:
            output.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in written:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def configure_notifications(
    env_path: Path,
    subscriptions_path: Path,
    *,
    input_fn: Input = input,
    secret_input: SecretInput = getpass.getpass,
    output: Output = print,
    secret_store: SecretStore | None = None,
    sender: Callable[[Settings, str], None] | None = None,
) -> str:
    mode_label = _numbered_choice(
        "Choose notification delivery",
        ("Discord", "Email", "Discord & Email"),
        input_fn,
        output,
    )
    mode = {
        "Discord": "discord",
        "Email": "email",
        "Discord & Email": "both",
    }[mode_label]
    base = load_settings(env_path, subscriptions_path, secret_store=secret_store)
    updates = {"NOTIFICATION_MODE": mode}
    secrets: dict[str, str] = {}
    discord_webhook: str | None = None
    if mode in {"discord", "both"}:
        discord_webhook = _required("Discord webhook URL", secret_input)
        secrets["discord_webhook"] = discord_webhook

    smtp_host = smtp_username = email_from = email_to = smtp_password = None
    smtp_port = 587
    smtp_use_tls = True
    if mode in {"email", "both"}:
        provider = _numbered_choice(
            "Choose email provider",
            ("Gmail", "Custom SMTP"),
            input_fn,
            output,
        )
        if provider == "Gmail":
            smtp_host = "smtp.gmail.com"
            smtp_username = _required("Gmail address", input_fn)
            email_from = smtp_username
            smtp_password = _required("Gmail app password", secret_input)
        else:
            smtp_host = _required("SMTP host", input_fn)
            smtp_port = int(_required("SMTP port", input_fn))
            smtp_username = _required("SMTP username", input_fn)
            email_from = _required("From address", input_fn)
            smtp_password = _required("SMTP password", secret_input)
        email_to = _required("Recipient address", input_fn)
        secrets["smtp_password"] = smtp_password
        updates.update(
            {
                "SMTP_HOST": smtp_host,
                "SMTP_PORT": str(smtp_port),
                "SMTP_USERNAME": smtp_username,
                "EMAIL_FROM": email_from,
                "EMAIL_TO": email_to,
                "SMTP_USE_TLS": str(smtp_use_tls).lower(),
            }
        )
    candidate = replace(
        base,
        discord_webhook=discord_webhook,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        email_from=email_from,
        email_to=email_to,
        smtp_use_tls=smtp_use_tls,
    )
    output("Sending required TEST notification(s)...")
    if sender:
        sender(candidate, mode)
    else:
        batch = render_batch([], utc_now(), candidate.display_timezone, test=True)
        if mode in {"discord", "both"}:
            DiscordChannel(discord_webhook or "").send(batch)
        if mode in {"email", "both"}:
            EmailChannel(candidate).send(batch)
    store = secret_store or default_secret_store()
    for key, value in secrets.items():
        store.set(key, value)
    write_env_settings(env_path, updates)
    output("Notification tests passed. Configuration saved securely.")
    return mode
