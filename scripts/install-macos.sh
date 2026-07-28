#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
releases_dir="$runtime_dir/releases"
agent_dir="$HOME/Library/LaunchAgents"
agent_path="$agent_dir/$label.plist"
python_version="3.13"
release_id="$(date -u +%Y%m%dT%H%M%SZ)"
candidate="$releases_dir/$release_id"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer supports macOS only." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Apple Refurb Reminder requires uv."
  echo "Official installer: https://docs.astral.sh/uv/getting-started/installation/"
  read -r -p "Run Astral's official uv installer now? [y/N] " install_uv
  if [[ "$install_uv" != "y" && "$install_uv" != "Y" ]]; then
    echo "Installation cancelled. Install uv and run this script again."
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv was installed but is not available on PATH. Open a new terminal and retry." >&2
    exit 1
  fi
fi

echo "Preparing isolated release $release_id..."
mkdir -p "$candidate" "$runtime_dir/data" "$runtime_dir/logs" "$agent_dir"
uv python install "$python_version"
uv venv --python "$python_version" "$candidate/.venv"
uv pip install --python "$candidate/.venv/bin/python" "$project_dir"

new_environment="false"
if [[ ! -f "$runtime_dir/.env" ]]; then
  {
    printf '%s\n' \
      "CHECK_INTERVAL_SECONDS=600" \
      "STATE_FILE=./data/state.json" \
      "LOG_DIR=./logs" \
      "DETAIL_CONCURRENCY=3"
  } >"$runtime_dir/.env"
  chmod 600 "$runtime_dir/.env"
  new_environment="true"
fi

if [[ ! -f "$runtime_dir/subscriptions.yaml" ]]; then
  echo
  echo "Starting the English watch-rule setup wizard..."
  (
    cd "$runtime_dir"
    "$candidate/.venv/bin/apple-refurb-reminder" setup
  )
fi

if [[ "$new_environment" == "true" ]] ||
  ! grep -Eq '^(NOTIFICATION_MODE|DISCORD_WEBHOOK|SMTP_HOST)=.+' "$runtime_dir/.env"; then
  echo
  echo "Configuring notification delivery..."
  (
    cd "$runtime_dir"
    "$candidate/.venv/bin/apple-refurb-reminder" setup notifications
  )
else
  echo "Existing notification configuration found; keeping it unchanged."
fi
(
  cd "$runtime_dir"
  "$candidate/.venv/bin/apple-refurb-reminder" validate-config
)

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
mv -fh "$runtime_dir/current.next" "$runtime_dir/current"

domain="gui/$(id -u)"
launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
if ! launchctl bootstrap "$domain" "$agent_path"; then
  echo "LaunchAgent installation failed. The release remains available at:" >&2
  echo "$candidate" >&2
  exit 1
fi
launchctl kickstart -k "$domain/$label"
sleep 2
if ! launchctl print "$domain/$label" | grep -q "state = running"; then
  launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
  echo "The service exited during its startup check." >&2
  echo "Review: $runtime_dir/logs/launchd.err.log" >&2
  exit 1
fi

echo
echo "Installation complete."
echo "Status: $project_dir/scripts/status-macos.sh"
echo "Logs: tail -f \"$runtime_dir/logs/monitor.log\""
