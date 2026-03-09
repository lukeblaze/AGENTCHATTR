"""Entry point — starts MCP server (port 8200) + web UI (port 8300)."""

import asyncio
import atexit
import secrets
import sys
import os
import subprocess
import shutil
import threading
import time
import logging
from pathlib import Path

# Ensure the project directory is on the import path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_auto_agents(config: dict) -> list[str]:
    """Return agents requested for auto-start via env var."""
    raw = (os.getenv("AGENTCHATTR_AUTO_START_AGENTS") or "").strip()
    if not raw:
        # Sensible default for 24/7 deployments: try all configured agents.
        return list((config.get("agents") or {}).keys())

    configured = list((config.get("agents") or {}).keys())
    configured_set = set(configured)
    selected: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        if name.lower() == "all":
            selected.extend(configured)
            continue
        if name in configured_set:
            selected.append(name)
        else:
            logging.getLogger(__name__).warning(
                "Ignoring AGENTCHATTR_AUTO_START_AGENTS entry '%s' (not in config)",
                name,
            )
    # Deduplicate while preserving order.
    return list(dict.fromkeys(selected))


def _start_wrapper_supervisor(config: dict) -> threading.Event | None:
    """Start and keep wrappers alive for selected agents."""
    log = logging.getLogger(__name__)
    if not _truthy(os.getenv("AGENTCHATTR_AUTO_START_WRAPPERS")):
        return None

    agents_to_run = _parse_auto_agents(config)
    if not agents_to_run:
        log.warning(
            "Auto-start requested but no agents selected. "
            "Set AGENTCHATTR_AUTO_START_AGENTS='name1,name2'."
        )
        return None

    stop_event = threading.Event()
    procs: dict[str, subprocess.Popen] = {}
    next_attempt: dict[str, float] = {}

    def _launch(agent_name: str) -> subprocess.Popen | None:
        agent_cfg = (config.get("agents") or {}).get(agent_name, {})
        is_api = agent_cfg.get("type") == "api"
        script = "wrapper_api.py" if is_api else "wrapper.py"

        # Preflight for CLI agents so missing binaries don't cause tight restart loops.
        if not is_api:
            command = str(agent_cfg.get("command") or "").strip()
            if not command or shutil.which(command) is None:
                log.warning(
                    "Skipping %s for now: command '%s' not found on PATH (retrying later)",
                    agent_name,
                    command or "<empty>",
                )
                return None

        cmd = [sys.executable, str(ROOT / script), agent_name]
        log.info("Starting wrapper for %s via %s", agent_name, script)
        return subprocess.Popen(cmd, cwd=str(ROOT), env=os.environ.copy())

    def _terminate_all():
        for name, proc in list(procs.items()):
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            finally:
                procs.pop(name, None)

    def _monitor():
        # Stagger startups slightly so register attempts don't all collide.
        for agent_name in agents_to_run:
            if stop_event.is_set():
                return
            try:
                launched = _launch(agent_name)
                if launched is not None:
                    procs[agent_name] = launched
                else:
                    next_attempt[agent_name] = time.time() + 60
            except Exception:
                log.exception("Failed to start wrapper for %s", agent_name)
                next_attempt[agent_name] = time.time() + 30
            time.sleep(1)

        while not stop_event.is_set():
            now = time.time()
            for agent_name in agents_to_run:
                proc = procs.get(agent_name)
                if proc is None:
                    if now < next_attempt.get(agent_name, 0):
                        continue
                    try:
                        launched = _launch(agent_name)
                        if launched is not None:
                            procs[agent_name] = launched
                            next_attempt.pop(agent_name, None)
                        else:
                            next_attempt[agent_name] = now + 60
                    except Exception:
                        log.exception("Failed to start wrapper for %s", agent_name)
                        next_attempt[agent_name] = now + 30
                    continue

                code = proc.poll()
                if code is not None:
                    log.warning("Wrapper for %s exited with code %s; restarting", agent_name, code)
                    procs.pop(agent_name, None)
                    # Backoff on failures to avoid hot restart loops.
                    next_attempt[agent_name] = now + 15
                    try:
                        launched = _launch(agent_name)
                        if launched is not None:
                            procs[agent_name] = launched
                            next_attempt.pop(agent_name, None)
                    except Exception:
                        log.exception("Failed to restart wrapper for %s", agent_name)
                        next_attempt[agent_name] = now + 30

            time.sleep(5)

        _terminate_all()

    threading.Thread(target=_monitor, daemon=True).start()
    atexit.register(lambda: stop_event.set())
    return stop_event


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from config_loader import load_config
    config_path = ROOT / "config.toml"
    if not config_path.exists():
        print(f"Error: {config_path} not found")
        sys.exit(1)

    config = load_config(ROOT)
    _start_wrapper_supervisor(config)

    # --- Security: generate a random session token (in-memory only) ---
    session_token = secrets.token_hex(32)

    # Configure the FastAPI app (creates shared store)
    from app import app, configure, set_event_loop, store as _store_ref
    configure(config, session_token=session_token)

    # Share stores with the MCP bridge
    from app import store, rules, summaries, jobs, room_settings, registry, router as app_router, agents as app_agents, session_engine, session_store
    import mcp_bridge
    mcp_bridge.store = store
    mcp_bridge.rules = rules
    mcp_bridge.summaries = summaries
    mcp_bridge.jobs = jobs
    mcp_bridge.room_settings = room_settings
    mcp_bridge.registry = registry
    mcp_bridge.config = config
    mcp_bridge.router = app_router
    mcp_bridge.agents = app_agents

    # Enable cursor and role persistence across restarts
    data_dir = ROOT / config.get("server", {}).get("data_dir", "./data")
    mcp_bridge._CURSORS_FILE = data_dir / "mcp_cursors.json"
    mcp_bridge._load_cursors()
    mcp_bridge._ROLES_FILE = data_dir / "roles.json"
    mcp_bridge._load_roles()

    # Start MCP servers in background threads
    http_port = config.get("mcp", {}).get("http_port", 8200)
    sse_port = config.get("mcp", {}).get("sse_port", 8201)
    mcp_bridge.mcp_http.settings.port = http_port
    mcp_bridge.mcp_sse.settings.port = sse_port

    threading.Thread(target=mcp_bridge.run_http_server, daemon=True).start()
    threading.Thread(target=mcp_bridge.run_sse_server, daemon=True).start()
    time.sleep(0.5)
    logging.getLogger(__name__).info("MCP streamable-http on port %d, SSE on port %d", http_port, sse_port)

    # Mount static files
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse

    static_dir = ROOT / "static"

    @app.get("/")
    async def index():
        # Read index.html fresh each request so changes take effect without restart.
        # Inject the session token into the HTML so the browser client can use it.
        # This is safe: same-origin policy prevents cross-origin pages from reading
        # the response body, so only the user's own browser tab gets the token.
        html = (static_dir / "index.html").read_text("utf-8")
        injected = html.replace(
            "</head>",
            f'<script>window.__SESSION_TOKEN__="{session_token}";</script>\n</head>',
        )
        return HTMLResponse(injected, headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Capture the event loop for the store→WebSocket bridge
    @app.on_event("startup")
    async def on_startup():
        set_event_loop(asyncio.get_running_loop())
        # Resume any sessions that were active before restart
        if session_engine:
            session_engine.resume_active_sessions()

    # Run web server
    import uvicorn
    host = config.get("server", {}).get("host", "127.0.0.1")
    port = config.get("server", {}).get("port", 8300)

    # --- Security: warn if binding to a non-localhost address ---
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"\n  !! SECURITY WARNING — binding to {host} !!")
        print("  This exposes agentchattr to your local network.")
        print()
        print("  Risks:")
        print("  - No TLS: traffic (including session token) is plaintext")
        print("  - Anyone on your network can sniff the token and gain full access")
        print("  - With the token, anyone can @mention agents and trigger tool execution")
        print("  - If agents run with auto-approve, this means remote code execution")
        print()
        print("  Only use this on a trusted home network. Never on public/shared WiFi.")
        allow_network = ("--allow-network" in sys.argv) or (os.getenv("AGENTCHATTR_ALLOW_NETWORK") == "1")
        if not allow_network:
            print("  Pass --allow-network to start anyway, or set host to 127.0.0.1.\n")
            sys.exit(1)
        else:
            print()
            if os.getenv("AGENTCHATTR_ALLOW_NETWORK") == "1":
                print("  AGENTCHATTR_ALLOW_NETWORK=1 set; proceeding non-interactively.\n")
            else:
                try:
                    confirm = input("  Type YES to accept these risks and start: ").strip()
                except (EOFError, KeyboardInterrupt):
                    confirm = ""
                if confirm != "YES":
                    print("  Aborted.\n")
                    sys.exit(1)

    print(f"\n  agentchattr")
    print(f"  Web UI:  http://{host}:{port}")
    print(f"  MCP HTTP: http://{host}:{http_port}/mcp  (Claude, Codex)")
    print(f"  MCP SSE:  http://{host}:{sse_port}/sse   (Gemini)")
    print(f"  Agents auto-trigger on @mention")
    print(f"\n  Session token: {session_token}\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

