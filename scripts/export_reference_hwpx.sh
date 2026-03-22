#!/bin/zsh
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <input.hwp> <output.hwpx>" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
osascript "$SCRIPT_DIR/export_reference_hwpx.applescript" "$1" "$2"
