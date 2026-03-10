#!/usr/bin/env bash
set -euo pipefail

# Wrapper launcher used by systemd unit.
# Usage: run_wrapper.sh <agent>

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <agent>"
  exit 2
fi

AGENT="$1"
REPO_DIR="${REPO_DIR:-$HOME/AGENTCHATTR}"
VENV_PY="$REPO_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing venv python at $VENV_PY"
  exit 1
fi

cd "$REPO_DIR"
exec "$VENV_PY" wrapper.py "$AGENT"
