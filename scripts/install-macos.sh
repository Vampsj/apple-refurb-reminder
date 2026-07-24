#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
agent_dir="$HOME/Library/LaunchAgents"
agent_path="$agent_dir/$label.plist"
python_version="3.13"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "このインストーラは macOS 専用です。" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "uv を Homebrew でインストールします..."
    brew install uv
  else
    echo "uv が必要です。先に https://docs.astral.sh/uv/ から uv をインストールしてください。" >&2
    exit 1
  fi
fi

echo "実行環境を準備しています..."
mkdir -p "$runtime_dir/data" "$runtime_dir/logs" "$agent_dir"
uv python install "$python_version"
uv venv --python "$python_version" "$runtime_dir/.venv"
uv pip install --python "$runtime_dir/.venv/bin/python" "$project_dir"
cp "$project_dir/subscriptions.yaml" "$runtime_dir/subscriptions.yaml"

if [[ ! -f "$runtime_dir/.env" ]]; then
  echo
  echo "通知設定を入力します。秘密情報は画面に再表示されません。"
  read -r -p "Discord Webhook URL: " discord_webhook
  read -r -p "Gmail 送信元（Emailを使わない場合は空欄）: " gmail_address

  smtp_password=""
  email_to=""
  smtp_host=""
  if [[ -n "$gmail_address" ]]; then
    smtp_host="smtp.gmail.com"
    read -r -s -p "Google 16桁アプリパスワード: " smtp_password
    echo
    read -r -p "通知先メールアドレス [$gmail_address]: " email_to
    email_to="${email_to:-$gmail_address}"
  fi

  old_umask="$(umask)"
  umask 077
  {
    printf '%s\n' \
      "APPLE_REGION=JP" \
      "APPLE_LOCALE=ja-JP" \
      "DISPLAY_TIMEZONE=Asia/Tokyo" \
      "CHECK_INTERVAL_SECONDS=600" \
      "STATE_FILE=./data/state.json" \
      "LOG_DIR=./logs" \
      "DETAIL_CONCURRENCY=3" \
      "" \
      "DISCORD_WEBHOOK=$discord_webhook" \
      "" \
      "SMTP_HOST=$smtp_host" \
      "SMTP_PORT=587" \
      "SMTP_USERNAME=$gmail_address" \
      "SMTP_PASSWORD=$smtp_password" \
      "EMAIL_FROM=$gmail_address" \
      "EMAIL_TO=$email_to" \
      "SMTP_USE_TLS=true"
  } >"$runtime_dir/.env"
  umask "$old_umask"
else
  echo "既存の .env を保持します。"
fi

chmod 600 "$runtime_dir/.env"

"$runtime_dir/.venv/bin/python" - "$runtime_dir" "$agent_path" <<'PY'
import plistlib
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
agent = Path(sys.argv[2])
payload = {
    "Label": "com.apple-refurb-reminder",
    "ProgramArguments": [str(runtime / ".venv/bin/apple-refurb-reminder"), "run"],
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

echo "設定を検証しています..."
(
  cd "$runtime_dir"
  .venv/bin/apple-refurb-reminder validate-config
)

domain="gui/$(id -u)"
launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
launchctl bootstrap "$domain" "$agent_path"
launchctl kickstart -k "$domain/$label"

echo
echo "インストールが完了しました。"
echo "状態確認: $project_dir/scripts/status-macos.sh"
echo "ログ: tail -f \"$runtime_dir/logs/monitor.log\""
