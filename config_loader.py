"""Shared config loader — merges config.toml + config.local.toml.

Used by run.py, wrapper.py, and wrapper_api.py so the server and all
wrappers see the same agent definitions.
"""

import tomllib
import os
from pathlib import Path

ROOT = Path(__file__).parent


def load_config(root: Path | None = None) -> dict:
    """Load config.toml and merge config.local.toml if it exists.

    config.local.toml is gitignored and intended for user-specific agents
    (e.g. local LLM endpoints) that shouldn't be committed.
    Only the [agents] section is merged — local entries are added alongside
    (not replacing) the agents defined in config.toml.
    """
    root = root or ROOT
    config_path = root / "config.toml"

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    def _merge_agents(extra_cfg: dict, source_name: str):
        local_agents = extra_cfg.get("agents", {})
        config_agents = config.setdefault("agents", {})
        for name, agent_cfg in local_agents.items():
            if name not in config_agents:
                config_agents[name] = agent_cfg
            else:
                print(f"  Warning: Ignoring agent '{name}' from {source_name} (already defined)")

    # Optional, deploy-friendly config file (tracked if desired).
    cloud_path = root / "config.cloud.toml"
    if cloud_path.exists():
        with open(cloud_path, "rb") as f:
            cloud = tomllib.load(f)
        _merge_agents(cloud, "config.cloud.toml")

    # User-local overrides (gitignored).
    local_path = root / "config.local.toml"
    if local_path.exists():
        with open(local_path, "rb") as f:
            local = tomllib.load(f)
        _merge_agents(local, "config.local.toml")

    # Environment overrides (useful for cloud deployment)
    server_cfg = config.setdefault("server", {})
    if os.getenv("AGENTCHATTR_HOST"):
        server_cfg["host"] = os.getenv("AGENTCHATTR_HOST")
    if os.getenv("AGENTCHATTR_PORT"):
        try:
            server_cfg["port"] = int(os.getenv("AGENTCHATTR_PORT"))
        except ValueError:
            pass
    elif os.getenv("PORT"):
        try:
            server_cfg["port"] = int(os.getenv("PORT"))
        except ValueError:
            pass

    bridge_cfg = config.setdefault("bridge", {})
    if os.getenv("AGENTCHATTR_BRIDGE_ENABLED"):
        bridge_cfg["enabled"] = os.getenv("AGENTCHATTR_BRIDGE_ENABLED", "").lower() in ("1", "true", "yes")
    if os.getenv("AGENTCHATTR_BRIDGE_KEY"):
        bridge_cfg["bridge_key"] = os.getenv("AGENTCHATTR_BRIDGE_KEY")
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        bridge_cfg["telegram_bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("WHATSAPP_ACCESS_TOKEN"):
        bridge_cfg["whatsapp_access_token"] = os.getenv("WHATSAPP_ACCESS_TOKEN")
    if os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
        bridge_cfg["whatsapp_phone_number_id"] = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if os.getenv("WHATSAPP_VERIFY_TOKEN"):
        bridge_cfg["whatsapp_verify_token"] = os.getenv("WHATSAPP_VERIFY_TOKEN")
    if os.getenv("WHATSAPP_FREE_UNTIL"):
        bridge_cfg["default_whatsapp_free_until"] = os.getenv("WHATSAPP_FREE_UNTIL")

    return config
