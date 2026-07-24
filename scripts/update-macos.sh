#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
agent_path="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"

if [[ ! -x "$runtime_dir/.venv/bin/python" || ! -f "$runtime_dir/.env" ]]; then
  echo "先に scripts/install-macos.sh を実行してください。" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv が見つかりません。" >&2
  exit 1
fi

uv pip install --python "$runtime_dir/.venv/bin/python" --reinstall "$project_dir"
cp "$project_dir/subscriptions.yaml" "$runtime_dir/subscriptions.yaml"
(
  cd "$runtime_dir"
  .venv/bin/apple-refurb-reminder validate-config
)

launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
launchctl bootstrap "$domain" "$agent_path"
launchctl kickstart -k "$domain/$label"
echo "更新して再起動しました。"
