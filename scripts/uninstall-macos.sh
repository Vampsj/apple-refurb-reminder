#!/bin/bash
set -euo pipefail

label="com.apple-refurb-reminder"
domain="gui/$(id -u)"
agent_path="$HOME/Library/LaunchAgents/$label.plist"
runtime_dir="$HOME/Library/Application Support/Apple Refurb Reminder"

launchctl bootout "$domain/$label" >/dev/null 2>&1 || true

echo "The LaunchAgent has been stopped."
echo "Configuration, secrets, releases, and state have been preserved."
echo "Runtime directory: $runtime_dir"
echo "LaunchAgent definition: $agent_path"
echo "Review these paths before removing anything manually."
