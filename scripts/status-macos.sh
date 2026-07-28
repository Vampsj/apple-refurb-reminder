#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"
domain="gui/$(id -u)"

launchctl print "$domain/$label"
echo
if [[ -L "$runtime_dir/current" ]]; then
  echo "Active release: $(readlink "$runtime_dir/current")"
fi
if [[ -f "$runtime_dir/logs/monitor.log" ]]; then
  echo "Latest monitor log:"
  tail -n 10 "$runtime_dir/logs/monitor.log"
fi
