#!/usr/bin/env python3
"""
Maestro-Orchestrator — Cross-platform setup script.

Works on Windows, macOS, and Linux. Requires only Python 3.10+ and Docker.
Replaces the bash-only setup.sh for universal compatibility.

Usage:
    python setup.py          # Build, start, wait for healthy, open browser
    python setup.py --no-browser   # Skip opening the browser
    python setup.py --dev    # Local dev mode (no Docker)
    python setup.py --verbose      # Show full Docker build output
"""

import itertools
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
    """Animated spinner with rotating status messages."""

    def __init__(self, messages: list[str], message_interval: float = 3.0):
        self._messages = messages[:]
        random.shuffle(self._messages)
        self._message_cycle = itertools.cycle(self._messages)
        self._message_interval = message_interval
        self._frames = SPINNER_FRAMES
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._final_message = ""

    def _animate(self) -> None:
        frame_cycle = itertools.cycle(self._frames)
        current_msg = next(self._message_cycle)
        last_switch = time.monotonic()

        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - last_switch >= self._message_interval:
                current_msg = next(self._message_cycle)
                last_switch = now

            frame = next(frame_cycle)
            line = f"\r  {frame} {current_msg} ..."
            sys.stdout.write(f"{line:<60}")
            sys.stdout.flush()
            self._stop_event.wait(0.08)

        # Clear the spinner line
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def start(self) -> "Spinner":
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


def check_deps() -> None:
    """Verify Docker and Docker Compose are installed."""
    missing = []

    if not shutil.which("docker"):
        missing.append("docker")

    if not find_compose_cmd():
        missing.append("docker compose")

    if missing:
        print(f"  Error: missing required tools: {', '.join(missing)}")
        print("  Install Docker: https://docs.docker.com/get-docker/")
        sys.exit(1)


def build_and_start(compose: list[str], verbose: bool = False) -> None:
    """Build and start containers, with spinner or verbose output."""
    if verbose:
        print("  Building and starting container ...\n")
        result = run(compose + ["up", "-d", "--build"])
        if result.returncode != 0:
            print("  Error: docker compose failed. Check the output above.")
            sys.exit(1)
        return

    spinner = Spinner(SETUP_MESSAGES).start()
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
    spinner = Spinner(HEALTH_MESSAGES, message_interval=4.0).start()

    try:
        for _ in range(HEALTH_RETRIES):
            try:
                import urllib.request
                with urllib.request.urlopen(HEALTH_ENDPOINT, timeout=3) as resp:
                    if resp.status == 200:
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


def open_browser(url: str) -> None:
    """Open the user's default browser."""
    try:
        webbrowser.open(url)
        print(f"  ✓ Browser opened to {url}")
    except Exception:
        print(f"  Open your browser to: {url}")


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

    build_and_start(find_compose_cmd(), verbose=verbose)
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
