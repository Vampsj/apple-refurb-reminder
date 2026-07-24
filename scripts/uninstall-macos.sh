#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
domain="gui/$(id -u)"
agent_path="$HOME/Library/LaunchAgents/$label.plist"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"

launchctl bootout "$domain/$label" >/dev/null 2>&1 || true

echo "LaunchAgent を停止しました。"
echo "設定と状態は次の場所に保持されています:"
echo "$runtime_dir"
echo "完全削除する場合は、内容を確認してからこのディレクトリを手動で削除してください。"
echo "LaunchAgent 定義: $agent_path"
