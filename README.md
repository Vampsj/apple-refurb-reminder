# Apple Refurb Reminder

[Simplified Chinese](docs/README.zh-CN.md) · [Japanese](docs/README.ja.md)

Apple Refurb Reminder is an independent command-line monitor for Apple Certified
Refurbished inventory. It checks matching products at a responsible interval and
sends immediate Discord, email, or combined notifications.

> [!IMPORTANT]
> The stable `v0.1.0` release monitors one MacBook Pro configuration in Japan.
> Multi-region V1 is under active development in Draft PR #1 and is not ready for
> unattended production use yet.

## V1 scope

- Apple Store regions: Japan, United States, mainland China, and Hong Kong
  (Traditional Chinese).
- Product categories: Mac computers, iPhone, and iPad.
- One region per installation and up to three independent watch rules.
- One exact model per rule; each applicable configuration field can be either
  one exact value or `Any`.
- Discord, email, or both. Gmail has a guided path; custom SMTP is available for
  advanced users.
- Notification language follows the selected Apple region.
- macOS 14 or later on Apple silicon and Intel is the supported platform.
  Linux CLI use is experimental. Windows is not supported.

Apple Watch, AirPods, Apple TV, HomePod, displays, and accessories are outside
the V1 scope.

## Development setup

Python 3.13 and `uv` are recommended:

```bash
uv sync --dev
cp .env.example .env
cp subscriptions.example.yaml subscriptions.yaml
```

If `uv` is unavailable, use a standard virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Create a watch rule with the English setup wizard:

```bash
.venv/bin/apple-refurb-reminder setup
```

Add or manage configuration later:

```bash
.venv/bin/apple-refurb-reminder setup add
.venv/bin/apple-refurb-reminder setup list
.venv/bin/apple-refurb-reminder setup edit RULE_ID
.venv/bin/apple-refurb-reminder setup remove RULE_ID
.venv/bin/apple-refurb-reminder setup notifications
.venv/bin/apple-refurb-reminder setup region US
```

The wizard loads current choices from the selected regional Apple catalog.
Manual entry remains available for configurations that are temporarily out of
stock. A region change archives the old rules and state, resets stock history,
and keeps notification settings.

## Safe verification

```bash
.venv/bin/apple-refurb-reminder validate-config
.venv/bin/apple-refurb-reminder check-once
.venv/bin/apple-refurb-reminder test-notifications
```

Start the long-running monitor:

```bash
.venv/bin/apple-refurb-reminder run
```

The default interval is 10 minutes. The hard minimum is 5 minutes.

## Secrets

V1 stores Discord webhooks and SMTP passwords in macOS Keychain. Experimental
Linux use falls back to a local secret file with `0600` permissions. Secrets are
never written to the generated `.env` file or echoed by the setup wizard.

Selected notification channels must pass a TEST delivery before the new
configuration is saved.

## Reliability

- Catalog data prefilters candidates before product detail pages are requested.
- Detail requests are shared across rules, limited to three concurrent requests,
  and cached persistently.
- Network errors, timeouts, unexpected pages, suspicious bot checks, and parser
  anomalies do not count as product absence.
- A category incident opens after three consecutive failures. Other successful
  categories continue normally, and a recovery notification is sent when the
  failed category works again.
- Old absent listings and unused detail cache entries are pruned after 30 days.
- The project collects no telemetry.

## Tests

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```

## Project status and releases

Stable releases use semantic versioning and Git tags. Updates are manual; V1
will include a backup, migration, validation, and rollback-safe macOS update
path before the Draft PR is eligible to merge.

## Disclaimer

This project is not affiliated with or endorsed by Apple Inc. Availability,
prices, and page structures can change without notice. Use the software
responsibly and comply with Apple's website terms and applicable local rules.
The software is provided without warranty under the [MIT License](LICENSE).
