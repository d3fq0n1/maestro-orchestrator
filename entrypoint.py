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
"""

import os
import subprocess
import sys


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


# ---------------------------------------------------------------------------
# Dialog GUI
# ---------------------------------------------------------------------------

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
    """Fallback text prompt when dialog is not available."""
    print()
    print("=" * 52)
    print("  Maestro-Orchestrator — Startup Mode Selection")
    print("=" * 52)
    print()
    print(f"  1) {WEB_LABEL}  —  {WEB_DESC}")
    print(f"  2) {CLI_LABEL}  —  {CLI_DESC}")
    print(f"  3) {TUI_LABEL}  —  {TUI_DESC}")
    print()
    try:
        answer = input("  Enter choice [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer == "2":
        return "cli"
    if answer == "3":
        return "tui"
    return "web"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
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
