#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script for an Ubuntu Oracle VM that will run CLI wrappers.
# Run as your normal user (with sudo access):
#   bash oracle/bootstrap_oracle_vm.sh

REPO_URL="${REPO_URL:-https://github.com/lukeblaze/AGENTCHATTR.git}"
REPO_DIR="${REPO_DIR:-$HOME/AGENTCHATTR}"
NODE_MAJOR="${NODE_MAJOR:-22}"

echo "[1/6] Installing OS dependencies"
sudo apt update
sudo apt install -y git curl tmux python3 python3-venv python3-pip ca-certificates

echo "[2/6] Installing Node.js ${NODE_MAJOR}.x"
curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | sudo -E bash -
sudo apt install -y nodejs

echo "[3/6] Cloning or updating repository"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "[4/6] Creating Python venv and installing deps"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "[5/6] Installing agent CLIs"
npm install -g @anthropic-ai/claude-code @openai/codex @google/gemini-cli kimi-code

echo "[6/6] Bootstrap complete"
cat <<EOF

Next steps:
1. Export Render URL for wrappers:
   export AGENTCHATTR_SERVER_URL="https://agentchattr.onrender.com"

2. Authenticate each CLI interactively:
   claude auth login
   codex
   gemini
   kimi --api-key <YOUR_GROQ_KEY>

3. Install systemd wrappers:
   bash "$REPO_DIR/oracle/install_wrapper_services.sh"

EOF
