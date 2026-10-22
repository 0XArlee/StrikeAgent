#!/bin/bash
# Build the bundle for the LXC: code, configs, unit files and tests. Never data, runs, secrets, the web or the
# proprietary indicator source (SmartFlowSignals.txt stays on the development machine).
# Usage (Git Bash, from the repo): deploy/bundle.sh [out.tgz]   then see docs/OPERATIONS.md "Updating the host".
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-smartflow.tgz}"
tar --exclude=__pycache__ --exclude='*.pyc' --exclude='*.jsonl' -czf "$out" README.md pyproject.toml config deploy src tests
echo "$out: $(du -h "$out" | cut -f1)"
