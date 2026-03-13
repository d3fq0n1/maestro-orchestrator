#!/usr/bin/env python3
"""
Maestro-Orchestrator — Cross-platform setup script.

Works on Windows, macOS, and Linux. Requires only Python 3.10+ and Docker.
Replaces the bash-only setup.sh for universal compatibility.

Usage:
    python setup.py                  # Build, start, wait for healthy, open browser
    python setup.py --no-browser     # Skip opening the browser
    python setup.py --dev            # Local dev mode (no Docker)
    python setup.py --verbose        # Show full Docker build output

Multi-instance management is available through the TUI (press M).
"""

import itertools
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

# Force UTF-8 output on Windows (winget/Microsoft Store Python defaults to the
# system code page, e.g. cp1252, which cannot encode the spinner/banner glyphs
# and raises UnicodeEncodeError before any useful output is shown).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Always run relative to the directory that contains this script so that
# Docker Compose can find docker-compose.yml regardless of where Python is
# invoked from (e.g. double-clicking on Windows, launchers, CI, etc.).
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

URL = "http://localhost:8000"
HEALTH_ENDPOINT = f"{URL}/api/health"
HEALTH_RETRIES = 30
HEALTH_DELAY = 2

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

SETUP_MESSAGES = [
    "Reticulating splines",
    "Cogitating deeply",
    "Herding containers",
    "Convincing electrons to cooperate",
    "Warming up the flux capacitor",
    "Asking Docker nicely",
    "Untangling dependencies",
    "Compiling good vibes",
    "Negotiating with the kernel",
    "Aligning bits and bytes",
    "Summoning daemons",
    "Consulting the oracle",
    "Feeding the hamsters",
    "Calibrating the cloud",
    "Brewing digital coffee",
    "Polishing the pixels",
    "Teaching containers to dance",
    "Defragmenting the astral plane",
    "Transcribing ancient scrolls",
    "Wrangling microservices",
    "Tuning the hypervisors",
    "Charging the lasers",
    "Resolving existential conflicts",
    "Spooling up the turbines",
]

HEALTH_MESSAGES = [
    "Poking Maestro gently",
    "Checking for signs of life",
    "Listening for a heartbeat",
    "Waiting for Maestro to wake up",
    "Knocking on port 8000",
    "Sending good vibes",
    "Whispering sweet nothings to the API",
    "Patiently lingering",
]


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

class Spinner:
    """Animated spinner with rotating status messages and optional progress bar.

    Progress can be driven in two ways:

    1. **Time-based (default)** – pass ``estimated_seconds`` and the bar fills
       along a curve that moves quickly at first and slows as it approaches
       ~95 %, giving a realistic feel without requiring actual progress data.
    2. **Manual** – call :meth:`set_progress` from the outside to set an exact
       0.0–1.0 value (useful when you know the real percentage, e.g. health-
       check retries).
    """

    BAR_WIDTH = 24  # characters inside the [ ] brackets

    def __init__(
        self,
        messages: list[str],
        message_interval: float = 3.0,
        estimated_seconds: float = 0,
    ):
        self._messages = messages[:]
        random.shuffle(self._messages)
        self._message_cycle = itertools.cycle(self._messages)
        self._message_interval = message_interval
        self._frames = SPINNER_FRAMES
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._final_message = ""
        # Progress state
        self._estimated_seconds = estimated_seconds
        self._manual_progress: float | None = None  # None → use time curve
        self._lock = threading.Lock()
        self._start_time = 0.0

    # -- public helpers ------------------------------------------------------

    def set_progress(self, value: float) -> None:
        """Manually set progress (0.0 – 1.0)."""
        with self._lock:
            self._manual_progress = max(0.0, min(1.0, value))

    # -- internal ------------------------------------------------------------

    def _current_progress(self) -> float:
        """Return the current progress fraction (0.0 – 1.0)."""
        with self._lock:
            if self._manual_progress is not None:
                return self._manual_progress
        if self._estimated_seconds <= 0:
            return 0.0
        elapsed = time.monotonic() - self._start_time
        # Asymptotic curve: approaches 1.0 but never quite reaches it.
        # At t == estimated_seconds the bar is at ~63 %; at 2× it's ~86 %.
        return 1.0 - math.exp(-elapsed / self._estimated_seconds)

    @staticmethod
    def _render_bar(progress: float, width: int) -> str:
        filled = int(progress * width)
        rest = width - filled
        pct = int(progress * 100)
        return f"[{'█' * filled}{'░' * rest}] {pct:>3}%"

    def _animate(self) -> None:
        frame_cycle = itertools.cycle(self._frames)
        current_msg = next(self._message_cycle)
        last_switch = time.monotonic()
        show_bar = self._estimated_seconds > 0 or self._manual_progress is not None

        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - last_switch >= self._message_interval:
                current_msg = next(self._message_cycle)
                last_switch = now

            frame = next(frame_cycle)
            if show_bar or self._manual_progress is not None:
                bar = self._render_bar(self._current_progress(), self.BAR_WIDTH)
                line = f"\r  {frame} {bar}  {current_msg} ..."
            else:
                line = f"\r  {frame} {current_msg} ..."
            sys.stdout.write(f"{line:<80}")
            sys.stdout.flush()
            self._stop_event.wait(0.08)

        # Clear the spinner line
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def start(self) -> "Spinner":
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def stop(self, final: str = "") -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        if final:
            print(final)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, letting stdout/stderr pass through to the terminal."""
    return subprocess.run(cmd, **kwargs)


def find_compose_cmd() -> list[str]:
    """Return the Docker Compose command as a list, or exit if not found."""
    for cmd in [["docker", "compose"], ["docker-compose"]]:
        try:
            result = subprocess.run(
                cmd + ["version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    return []


def is_daemon_running() -> bool:
    """Return True if the Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_permission_denied() -> bool:
    """Return True if docker info fails specifically due to a permission error."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").lower()
            return "permission denied" in stderr or "connect: permission denied" in stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def _daemon_start_hint() -> str:
    """Return a platform-specific hint for starting the Docker daemon."""
    system = platform.system()
    if system == "Darwin":
        return "  Hint: open -a Docker          (or launch Docker Desktop from Applications)"
    elif system == "Windows":
        return '  Hint: Start Docker Desktop from the Start menu or taskbar'
    else:
        return "  Hint: sudo systemctl start docker   (or launch Docker Desktop)"


def wait_for_daemon(timeout: int = 60) -> bool:
    """Wait up to *timeout* seconds for the Docker daemon to become reachable."""
    deadline = time.monotonic() + timeout
    interval = 2
    while time.monotonic() < deadline:
        if is_daemon_running():
            return True
        time.sleep(interval)
    return False


def check_deps() -> None:
    """Verify Docker and Docker Compose are installed, and the daemon is running."""
    missing = []

    if not shutil.which("docker"):
        missing.append("docker")

    if not find_compose_cmd():
        missing.append("docker compose")

    if missing:
        print(f"  Warning: missing tools: {', '.join(missing)}")
        print("  Install Docker: https://docs.docker.com/get-docker/")
        print()
        print("  Alternatively, run without Docker:")
        print("    python setup.py --dev")
        print()

        # Interactive terminal: offer to switch to dev mode; non-interactive: exit.
        if sys.stdin.isatty():
            try:
                answer = input("  Switch to local dev mode? [y/N] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                sys.exit(1)
            if answer == "y":
                dev_setup()
                return
        sys.exit(1)

    # --- Docker daemon reachability check ---
    if not is_daemon_running():
        if _docker_permission_denied():
            print("  Error: Docker is running but this user cannot access it.")
            print()
            print("  Fix: add your user to the docker group, then log out and back in:")
            print("    sudo usermod -aG docker $USER")
            print("    newgrp docker   # apply without logging out (current shell only)")
            print()
        else:
            print("  Error: Docker is installed but the daemon is not running.")
            print()
            print(_daemon_start_hint())
            print()

        # Interactive terminal: offer to wait; non-interactive: just exit.
        if sys.stdin.isatty():
            try:
                answer = input("  Start Docker and press Enter to continue (or Ctrl+C to quit) ... ")
            except (KeyboardInterrupt, EOFError):
                print()
                sys.exit(1)

            print()
            spinner = Spinner(["Waiting for Docker daemon to be ready"], estimated_seconds=60).start()
            ok = wait_for_daemon(timeout=120)
            spinner.stop()

            if not ok:
                print("  Error: Docker daemon did not become available within 120 seconds.")
                print("  Please make sure Docker Desktop (or the docker service) is fully started, then try again.")
                sys.exit(1)
            print("  ✓ Docker daemon is now running")
        else:
            sys.exit(1)


def cleanup_stale_containers(compose: list[str], port: str = "8000") -> None:
    """Stop prior Maestro containers and kill processes holding the port."""
    # 1. docker compose down (handles the normal case)
    subprocess.run(
        compose + ["down", "--remove-orphans"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 2. Force-remove any maestro-orchestrator containers that survived
    #    compose down (e.g. containers with mangled names from interrupted runs).
    try:
        result = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "name=maestro-orchestrator"],
            capture_output=True, text=True,
        )
        stale = result.stdout.strip()
        if stale:
            subprocess.run(
                ["docker", "rm", "-f"] + stale.split(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

    # 3. Stop any Docker container (from any project) holding the port.
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"publish={port}"],
            capture_output=True, text=True,
        )
        stale = result.stdout.strip()
        if stale:
            subprocess.run(
                ["docker", "rm", "-f"] + stale.split(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass

    # 4. Kill leftover host processes holding the port (stale uvicorn, etc.).
    if shutil.which("lsof"):
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True,
            )
            pids = result.stdout.strip()
            if pids:
                for pid in pids.split():
                    subprocess.run(
                        ["kill", "-9", pid],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                time.sleep(1)
        except Exception:
            pass
    elif shutil.which("ss"):
        try:
            result = subprocess.run(
                ["ss", "-tlnp", f"sport = :{port}"],
                capture_output=True, text=True,
            )
            import re
            pids = re.findall(r'pid=(\d+)', result.stdout)
            if pids:
                for pid in pids:
                    subprocess.run(
                        ["kill", "-9", pid],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                time.sleep(1)
        except Exception:
            pass


def build_and_start(compose: list[str], verbose: bool = False) -> None:
    """Build and start containers, with spinner or verbose output."""
    # Ensure .env exists so docker-compose doesn't error on a missing env_file.
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        open(env_path, "a").close()
    if verbose:
        print("  Building and starting container ...\n")
        result = run(compose + ["up", "-d", "--build"])
        if result.returncode != 0:
            print("  Error: docker compose failed. Check the output above.")
            sys.exit(1)
        return

    # estimated_seconds drives the progress bar curve.  On a Raspberry Pi a
    # first build can easily take 5-10 minutes; 300 s keeps the bar moving at
    # a reassuring pace without stalling early.
    spinner = Spinner(SETUP_MESSAGES, estimated_seconds=300).start()
    logfile = os.path.join(PROJECT_ROOT, ".setup-build.log")
    try:
        with open(logfile, "w") as log:
            result = subprocess.run(
                compose + ["up", "-d", "--build"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    finally:
        spinner.stop()

    if result.returncode != 0:
        print("  Error: Docker build failed. Here's the tail of the log:\n")
        try:
            with open(logfile) as f:
                lines = f.readlines()
            for line in lines[-30:]:
                print(f"    {line}", end="")
        except Exception:
            pass
        print(f"\n  Full log: {logfile}")
        sys.exit(1)

    # Clean up log on success
    try:
        os.remove(logfile)
    except OSError:
        pass

    print("  ✓ Container built and started")


def wait_for_healthy() -> bool:
    """Poll the health endpoint with a spinner until it responds or times out."""
    spinner = Spinner(HEALTH_MESSAGES, message_interval=4.0)
    spinner.set_progress(0.0)
    spinner.start()

    try:
        for attempt in range(HEALTH_RETRIES):
            spinner.set_progress(attempt / HEALTH_RETRIES)
            try:
                import urllib.request
                with urllib.request.urlopen(HEALTH_ENDPOINT, timeout=3) as resp:
                    if resp.status == 200:
                        spinner.set_progress(1.0)
                        spinner.stop("  ✓ Maestro is up and healthy")
                        return True
            except Exception:
                pass
            time.sleep(HEALTH_DELAY)
    except KeyboardInterrupt:
        spinner.stop()
        raise

    spinner.stop()
    total = HEALTH_RETRIES * HEALTH_DELAY
    print(f"  ⚠ Maestro did not respond within {total}s.")
    if platform.system() == "Windows":
        print("  Check logs with: docker compose logs -f")
    else:
        print("  Check logs with: make logs")
    return False


def _has_graphical_browser() -> bool:
    """Return True if a graphical web browser is available.

    When only text browsers (lynx, w3m, links, elinks) are available,
    opening the React dashboard is not useful — the TUI is a better choice.
    """
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


def _install_tui_deps() -> None:
    """Install the local Python packages required by the TUI (textual, rich)."""
    try:
        import textual  # noqa: F401
        import rich  # noqa: F401
    except ImportError:
        print("  Installing TUI dependencies (textual, rich) ...")
        pkgs = ["textual>=0.85.0", "rich>=13.0.0"]
        # First attempt — standard install
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *pkgs],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            print("  ✓ TUI dependencies installed")
            return
        # Second attempt — PEP 668 externally-managed environments (Debian/Ubuntu/Raspbian)
        # require --break-system-packages to install into the system Python.
        stderr = result.stderr.decode(errors="replace")
        if "externally-managed-environment" in stderr or "externally managed" in stderr.lower():
            result2 = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", *pkgs],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if result2.returncode == 0:
                print("  ✓ TUI dependencies installed")
                return
            stderr = result2.stderr.decode(errors="replace").strip()
        else:
            stderr = stderr.strip()
        print(f"  ⚠ Could not install TUI dependencies: {stderr}")
        print("  You can install them manually: pip install textual rich")
        print("  Or: pip install --break-system-packages textual rich")


def open_browser(url: str) -> None:
    """Open the user's default browser, or offer an interactive mode selector."""
    if not _has_graphical_browser():
        _install_tui_deps()
        print(f"  No graphical browser detected.")
        print(f"  The Maestro API is running at {url}")
        print()

        if sys.stdin.isatty():
            _launch_interactive_selector()
        else:
            print("  To use Maestro from this terminal, launch the TUI dashboard:")
            print("    python -m maestro.tui --mode http")
            print()
            print("  Or launch the interactive CLI:")
            print("    python -m maestro.cli")
        return
    try:
        webbrowser.open(url)
        print(f"  ✓ Browser opened to {url}")
    except Exception:
        print(f"  Open your browser to: {url}")


def _launch_interactive_selector() -> None:
    """Show the interactive mode selector and launch the chosen mode."""
    from maestro.selector import interactive_select, Option

    options = [
        Option("tui", "TUI Dashboard", "Terminal dashboard (optimized for SoC / Raspi)"),
        Option("cli", "Interactive CLI", "Command-line REPL with full pipeline access"),
    ]

    choice = interactive_select(options, title="Maestro-Orchestrator  —  Launch Mode")

    if choice == "tui":
        print("  Launching TUI Dashboard ...")
        print()
        # Import and run inline to avoid subprocess overhead
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
        sys.path.insert(0, PROJECT_ROOT)
        from maestro.tui.__main__ import main as tui_main
        tui_main()
    elif choice == "cli":
        print("  Launching Interactive CLI ...")
        print()
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
        sys.path.insert(0, PROJECT_ROOT)
        from maestro.cli import interactive_loop
        interactive_loop()


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

BANNER = r"""
       ___  ___                _
       |  \/  |               | |
       | .  . | __ _  ___  ___| |_ _ __ ___
       | |\/| |/ _` |/ _ \/ __| __| '__/ _ \
       | |  | | (_| |  __/\__ \ |_| | | (_) |
       \_|  |_/\__,_|\___||___/\__|_|  \___/

          ♫  Orchestrator Setup  ♫
"""


def docker_setup(skip_browser: bool = False, verbose: bool = False) -> None:
    """Build and start the container, wait for healthy, open browser."""
    print(BANNER)

    check_deps()
    print("  ✓ Dependencies verified\n")

    compose = find_compose_cmd()
    port = os.environ.get("MAESTRO_PORT", "8000")

    print("  Stopping prior sessions ...")
    cleanup_stale_containers(compose, port)
    print("  ✓ Clean slate\n")

    build_and_start(compose, verbose=verbose)
    print()

    healthy = wait_for_healthy()
    print()

    if healthy and not skip_browser:
        open_browser(URL)
        print()

    print(f"  Maestro is running at {URL}")
    print()
    if platform.system() != "Windows":
        print("  Useful commands:")
        print("    make logs     Tail container logs")
        print("    make status   Check container health")
        print("    make down     Stop the container")
        print()
        print("  Multi-instance: launch the TUI and press M")
    else:
        print("  Useful commands:")
        print("    docker compose logs -f      Tail container logs")
        print("    docker compose ps           Check container status")
        print("    docker compose down         Stop the container")
    print()


def dev_setup() -> None:
    """Start local dev servers (backend + frontend) without Docker."""
    print()
    print("  Starting local development servers ...")
    print()

    # Check for backend requirements
    backend_req = os.path.join("backend", "requirements.txt")
    if not os.path.exists(backend_req):
        print("  Error: backend/requirements.txt not found. Are you in the project root?")
        sys.exit(1)

    print("  Installing backend dependencies ...")
    run([sys.executable, "-m", "pip", "install", "-r", backend_req])

    # Check for frontend
    frontend_pkg = os.path.join("frontend", "package.json")
    has_frontend = os.path.exists(frontend_pkg) and shutil.which("npm")

    if has_frontend:
        print("  Installing frontend dependencies ...")
        run(["npm", "install"], cwd="frontend")

    print()
    print("  Starting backend on :8000 ...")

    # Start backend
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd="backend",
    )

    frontend_proc = None
    if has_frontend:
        print("  Starting frontend on :5173 ...")
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="frontend",
        )

    print()
    print("  Backend:  http://localhost:8000")
    if frontend_proc:
        print("  Frontend: http://localhost:5173")
    print("  Press Ctrl+C to stop.")
    print()

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n  Shutting down ...")
        backend_proc.terminate()
        if frontend_proc:
            frontend_proc.terminate()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--dev" in args:
        dev_setup()
    else:
        skip_browser = "--no-browser" in args
        verbose = "--verbose" in args
        docker_setup(skip_browser=skip_browser, verbose=verbose)


if __name__ == "__main__":
    main()
