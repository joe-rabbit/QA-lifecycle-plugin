#!/usr/bin/env bash
# Package the Claude plugin as dist/qa-lifecycle.plugin
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$root/dist"
rm -f "$root/dist/qa-lifecycle.plugin"
cd "$root/plugins/qa-lifecycle"
zip -qr "$root/dist/qa-lifecycle.plugin" . -x "*.DS_Store" -x "*__pycache__*"
echo "wrote dist/qa-lifecycle.plugin"
