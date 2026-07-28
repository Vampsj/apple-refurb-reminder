#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
releases_dir="$runtime_dir/releases"
agent_path="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"
python_version="3.13"
release_id="$(date -u +%Y%m%dT%H%M%SZ)"
candidate="$releases_dir/$release_id"
backup_dir="$runtime_dir/backups/$release_id"
previous=""

restore_previous() {
  cp "$backup_dir/.env" "$runtime_dir/.env"
  cp "$backup_dir/subscriptions.yaml" "$runtime_dir/subscriptions.yaml"
  if [[ -n "$previous" ]]; then
    ln -s "$previous" "$runtime_dir/current.rollback"
    mv -fh "$runtime_dir/current.rollback" "$runtime_dir/current"
    launchctl bootstrap "$domain" "$agent_path"
    launchctl kickstart -k "$domain/$label"
  fi
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This updater supports macOS only." >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. See https://docs.astral.sh/uv/" >&2
  exit 1
fi
if [[ ! -f "$runtime_dir/.env" || ! -f "$runtime_dir/subscriptions.yaml" ]]; then
  echo "No existing installation was found. Run scripts/install-macos.sh first." >&2
  exit 1
fi

mkdir -p "$candidate" "$backup_dir"
cp "$runtime_dir/.env" "$backup_dir/.env"
cp "$runtime_dir/subscriptions.yaml" "$backup_dir/subscriptions.yaml"
if [[ -f "$runtime_dir/data/state.json" ]]; then
  cp "$runtime_dir/data/state.json" "$backup_dir/state.json"
fi

echo "Building and validating candidate release $release_id..."
uv python install "$python_version"
uv venv --python "$python_version" "$candidate/.venv"
uv pip install --python "$candidate/.venv/bin/python" "$project_dir"
cp "$runtime_dir/subscriptions.yaml" "$candidate/subscriptions.yaml"
cp "$runtime_dir/.env" "$candidate/.env"
(
  cd "$runtime_dir"
  "$candidate/.venv/bin/apple-refurb-reminder" \
    --env "$candidate/.env" \
    --subscriptions "$candidate/subscriptions.yaml" setup migrate
  "$candidate/.venv/bin/apple-refurb-reminder" \
    --env "$candidate/.env" \
    --subscriptions "$candidate/subscriptions.yaml" validate-config
)

if [[ -L "$runtime_dir/current" ]]; then
  previous="$(readlink "$runtime_dir/current")"
elif [[ -x "$runtime_dir/.venv/bin/apple-refurb-reminder" ]]; then
  previous="$runtime_dir"
fi

"$candidate/.venv/bin/python" - "$runtime_dir" "$agent_path" <<'PY'
import plistlib
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
agent = Path(sys.argv[2])
payload = {
    "Label": "com.apple-refurb-reminder",
    "ProgramArguments": [
        str(runtime / "current/.venv/bin/apple-refurb-reminder"),
        "run",
    ],
    "WorkingDirectory": str(runtime),
    "RunAtLoad": True,
    "KeepAlive": {"SuccessfulExit": False},
    "ProcessType": "Background",
    "ThrottleInterval": 30,
    "StandardOutPath": str(runtime / "logs/launchd.out.log"),
    "StandardErrorPath": str(runtime / "logs/launchd.err.log"),
}
with agent.open("wb") as handle:
    plistlib.dump(payload, handle)
PY

ln -s "$candidate" "$runtime_dir/current.next"
cp "$candidate/subscriptions.yaml" "$runtime_dir/subscriptions.next.yaml"
cp "$candidate/.env" "$runtime_dir/.env.next"
launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
mv -fh "$runtime_dir/current.next" "$runtime_dir/current"
mv -f "$runtime_dir/subscriptions.next.yaml" "$runtime_dir/subscriptions.yaml"
mv -f "$runtime_dir/.env.next" "$runtime_dir/.env"

if ! launchctl bootstrap "$domain" "$agent_path"; then
  echo "The new release failed to start. Restoring the previous release..." >&2
  restore_previous
  exit 1
fi
launchctl kickstart -k "$domain/$label"
sleep 2
if ! launchctl print "$domain/$label" | grep -q "state = running"; then
  echo "The new release exited during its startup check. Restoring the previous release..." >&2
  launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
  restore_previous
  exit 1
fi

echo "Update complete."
echo "Active release: $candidate"
echo "Configuration backup: $backup_dir"
