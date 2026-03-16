#!/usr/bin/env python3
"""
Maestro-Orchestrator Unified Startup Wrapper.

Presents a dialog-based GUI on container startup so users can choose
between the Web-UI (FastAPI + React dashboard), the interactive CLI,
or the TUI dashboard (optimized for SoC devices like Raspberry Pi 5).
When no TTY is attached (e.g., CI, headless deployment), defaults to
the Web-UI automatically.

Environment variable override:
    MAESTRO_MODE=web   -> skip dialog, launch Web-UI directly
    MAESTRO_MODE=cli   -> skip dialog, launch CLI directly
    MAESTRO_MODE=tui   -> skip dialog, launch TUI directly

Cluster roles (NODE_ROLE env var):
    NODE_ROLE=orchestrator -> start as cluster coordinator
    NODE_ROLE=shard        -> start as shard worker (skips dialog)
"""

import os
import subprocess
import sys
import webbrowser


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DIALOG_TITLE = "Maestro-Orchestrator"
DIALOG_TEXT = (
    "Welcome to Maestro-Orchestrator.\n\n"
    "Select how you would like to run the system:"
)
WEB_LABEL = "Web-UI"
WEB_DESC = "Launch the full dashboard (API + React UI on port 8000)"
CLI_LABEL = "CLI"
CLI_DESC = "Launch the interactive command-line interface"
TUI_LABEL = "TUI"
TUI_DESC = "Launch the terminal dashboard (optimized for SoC / Raspi5)"

# ---------------------------------------------------------------------------
# Mode launchers
# ---------------------------------------------------------------------------

def launch_web():
    """Start the FastAPI/Uvicorn server (Web-UI + API)."""
    print("[Maestro] Starting Web-UI on http://0.0.0.0:8000 ...")
    os.chdir(os.path.join(os.path.dirname(__file__), "backend"))
    os.execvp("uvicorn", ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"])


def launch_cli():
    """Start the interactive CLI session."""
    # Import path fixup — same as orchestrator_foundry.py
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    sys.path.insert(0, os.path.dirname(__file__))

    from maestro.cli import interactive_loop
    interactive_loop()


def launch_tui():
    """Start the TUI dashboard (Textual-based, optimized for SoC devices)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    sys.path.insert(0, os.path.dirname(__file__))

    from maestro.tui.__main__ import main as tui_main
    tui_main()


def launch_shard_worker():
    """Start as a shard worker node — runs the node_server FastAPI app.

    Reads NODE_ID, ORCHESTRATOR_URL, SHARD_INDEX, SHARD_COUNT directly
    from environment variables to avoid importing the maestro package at
    the module level (which would trigger plugin/selector init and
    corrupt the terminal).
    """
    node_id = os.environ.get("NODE_ID", "shard-unknown")
    shard_index = os.environ.get("SHARD_INDEX", "?")
    shard_count = os.environ.get("SHARD_COUNT", "?")
    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "")

    print(f"[Maestro] Starting shard worker node: {node_id} "
          f"(shard {shard_index}/{shard_count})")

    # Propagate to the env keys the node_server expects
    os.environ.setdefault("MAESTRO_NODE_ID", node_id)
    if orchestrator_url:
        os.environ.setdefault("MAESTRO_ORCHESTRATOR_URL", orchestrator_url)

    # chdir to project root so "maestro.node_server" is importable
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    os.execvp("uvicorn", [
        "uvicorn", "maestro.node_server:app",
        "--host", "0.0.0.0", "--port", "8000",
    ])


# ---------------------------------------------------------------------------
# Dialog GUI
# ---------------------------------------------------------------------------

def _has_graphical_browser() -> bool:
    """Return True if a graphical web browser is available."""
    try:
        browser = webbrowser.get()
        browser_name = getattr(browser, "name", "") or type(browser).__name__.lower()
        text_only = ("lynx", "w3m", "links", "elinks", "www-browser")
        for t in text_only:
            if t in browser_name:
                return False
        return True
    except webbrowser.Error:
        return False


def _dialog_available() -> bool:
    """Check whether the `dialog` utility is installed."""
    try:
        subprocess.run(
            ["dialog", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def show_dialog() -> str:
    """
    Display a dialog menu and return the user's choice ('web' or 'cli').
    Falls back to a plain input() prompt when dialog is unavailable.
    """
    if _dialog_available():
        return _dialog_gui()
    return _plain_prompt()


def _dialog_gui() -> str:
    """Use the ncurses `dialog` utility for a graphical menu."""
    cmd = [
        "dialog",
        "--clear",
        "--title", DIALOG_TITLE,
        "--menu", DIALOG_TEXT,
        18, 65, 3,
        "web", f"{WEB_LABEL}  —  {WEB_DESC}",
        "cli", f"{CLI_LABEL}  —  {CLI_DESC}",
        "tui", f"{TUI_LABEL}  —  {TUI_DESC}",
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE)
    # dialog writes the selection to stderr
    choice = result.stderr.decode().strip().lower()

    # Clear the screen after dialog closes
    subprocess.run(["clear"], check=False)

    if choice in ("web", "cli", "tui"):
        return choice

    # User pressed Cancel or Escape — default to web
    print("[Maestro] No selection made — defaulting to Web-UI.")
    return "web"


def _plain_prompt() -> str:
    """Interactive mode selector with arrow-key navigation.

    Falls back to a numbered prompt when raw terminal input is
    unavailable.
    """
    from maestro.selector import interactive_select
    return interactive_select(title="Maestro-Orchestrator  —  Startup Mode")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # ── Cluster role detection (earliest possible point) ──────────────
    # Read NODE_ROLE directly from env to decide the startup path
    # BEFORE importing any maestro modules. Importing maestro triggers
    # the plugin manager / selector init chain which can write ANSI
    # escape codes and corrupt the terminal if it happens too early.
    node_role = os.environ.get("NODE_ROLE", "").lower().strip()

    if node_role == "shard":
        # Shard workers skip the mode dialog entirely and launch the
        # node_server via uvicorn.  No maestro imports needed here.
        launch_shard_worker()
        return

    if node_role == "orchestrator":
        node_id = os.environ.get("NODE_ID", "primary")
        shard_count = os.environ.get("SHARD_COUNT", "1")
        print(f"[Maestro] Starting as cluster orchestrator: {node_id} "
              f"(coordinating {shard_count} shards)")

    # Ensure required Python packages are installed before any mode launches.
    # Inside Docker this is a no-op (packages are baked into the image), but
    # when running the entrypoint directly on the host this catches missing deps.
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, project_root)
        sys.path.insert(0, os.path.join(project_root, "backend"))
        from maestro.dependency_resolver import ensure_packages
        installed = ensure_packages(quiet=True)
        if installed:
            print(f"[Maestro] Installed missing packages: {', '.join(installed)}")
    except Exception:
        pass  # Never block startup due to install failures

    # Allow environment variable to bypass the dialog entirely
    env_mode = os.environ.get("MAESTRO_MODE", "").lower()
    if env_mode in ("web", "cli", "tui"):
        mode = env_mode
    elif sys.stdin.isatty():
        mode = show_dialog()
    else:
        # No TTY (e.g., docker-compose up without -it) -> default to web
        mode = "web"

    # Check for updates on startup (non-blocking, notify-only)
    try:
        from maestro.updater import startup_check
        startup_check()
    except Exception:
        pass  # Never block startup due to update check failure

    if mode == "cli":
        launch_cli()
    elif mode == "tui":
        launch_tui()
    else:
        launch_web()


if __name__ == "__main__":
    main()
