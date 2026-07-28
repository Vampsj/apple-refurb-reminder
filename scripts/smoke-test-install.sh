#!/bin/bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for the isolated installation smoke test." >&2
  exit 1
fi

smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/apple-refurb-smoke.XXXXXX")"
cleanup() {
  if [[ "$smoke_root" == "${TMPDIR:-/tmp}/apple-refurb-smoke."* ]]; then
    rm -rf "$smoke_root"
  fi
}
trap cleanup EXIT

runtime_dir="$smoke_root/runtime"
release_dir="$smoke_root/release"
mkdir -p "$runtime_dir/data" "$runtime_dir/logs" "$release_dir"

uv venv --python 3.13 "$release_dir/.venv"
uv pip install --python "$release_dir/.venv/bin/python" "$project_dir"

cat >"$runtime_dir/.env" <<'EOF'
CHECK_INTERVAL_SECONDS=600
STATE_FILE=./data/state.json
LOG_DIR=./logs
DETAIL_CONCURRENCY=3
EOF

cat >"$runtime_dir/subscriptions.yaml" <<'EOF'
schema_version: 2
region: US
rules:
  - id: smoke-test
    category: iphone
    model: iPhone 16 Pro
    storage: 256GB
EOF

(
  cd "$runtime_dir"
  validation_output="$("$release_dir/.venv/bin/apple-refurb-reminder" validate-config)"
  rules_output="$("$release_dir/.venv/bin/apple-refurb-reminder" setup list)"
  echo "$validation_output"
  echo "$rules_output"
  [[ "$validation_output" == "Configuration is valid "* ]]
  [[ "$rules_output" == *"Region: US"* ]]
  [[ "$rules_output" == *"smoke-test: iphone / iPhone 16 Pro"* ]]
  "$release_dir/.venv/bin/python" -c "import apple_refurb_reminder"
)

echo "Isolated installation smoke test passed."
