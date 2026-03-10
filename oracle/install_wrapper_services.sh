#!/usr/bin/env bash
set -euo pipefail

# Install and enable systemd services for wrapper CLIs on Oracle VM.
# Run as your normal user after CLI auth is complete.

REPO_DIR="${REPO_DIR:-$HOME/AGENTCHATTR}"
UNIT_SRC="$REPO_DIR/oracle/systemd/agentchattr-wrapper@.service"
UNIT_DST_DIR="$HOME/.config/systemd/user"
ENV_FILE="$REPO_DIR/oracle/agentchattr.env"

mkdir -p "$UNIT_DST_DIR"
cp "$UNIT_SRC" "$UNIT_DST_DIR/agentchattr-wrapper@.service"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
# Required: your public server URL (Render endpoint)
AGENTCHATTR_SERVER_URL=https://agentchattr.onrender.com

# Optional: force fallback routing map from wrappers (if needed)
# AGENTCHATTR_OFFLINE_FALLBACK_MAP={"claude":"openrouter","codex":"openrouter","gemini":"openrouter","kimi":"openrouter"}
EOF
  echo "Created $ENV_FILE (edit values before starting services)."
fi

chmod +x "$REPO_DIR/oracle/run_wrapper.sh"

systemctl --user daemon-reload

# Enable linger so user services survive logout/reboot.
if command -v loginctl >/dev/null 2>&1; then
  sudo loginctl enable-linger "$USER" || true
fi

# Configure which wrappers to run.
AGENTS=(claude codex gemini kimi)
if [[ -n "${AGENT_LIST:-}" ]]; then
  IFS=',' read -r -a AGENTS <<< "${AGENT_LIST}"
fi

for a in "${AGENTS[@]}"; do
  a_trimmed="$(echo "$a" | xargs)"
  [[ -z "$a_trimmed" ]] && continue
  systemctl --user enable "agentchattr-wrapper@${a_trimmed}.service"
  systemctl --user restart "agentchattr-wrapper@${a_trimmed}.service"
  echo "Started wrapper service: ${a_trimmed}"
done

cat <<EOF

Done. Check status with:
  systemctl --user status agentchattr-wrapper@claude.service
  systemctl --user status agentchattr-wrapper@codex.service
  systemctl --user status agentchattr-wrapper@gemini.service
  systemctl --user status agentchattr-wrapper@kimi.service

Logs:
  journalctl --user -u agentchattr-wrapper@claude.service -f

EOF
