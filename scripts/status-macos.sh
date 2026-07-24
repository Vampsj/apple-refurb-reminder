#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
domain="gui/$(id -u)"

launchctl print "$domain/$label"
echo
if [[ -f "$runtime_dir/logs/monitor.log" ]]; then
  echo "最新の監視ログ:"
  tail -n 10 "$runtime_dir/logs/monitor.log"
fi
