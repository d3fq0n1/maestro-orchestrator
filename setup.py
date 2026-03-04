#!/usr/bin/env python3
"""
Maestro-Orchestrator — Cross-platform setup script.

Works on Windows, macOS, and Linux. Requires only Python 3.10+ and Docker.
Replaces the bash-only setup.sh for universal compatibility.

Usage:
    python setup.py          # Build, start, wait for healthy, open browser
    python setup.py --no-browser   # Skip opening the browser
    python setup.py --dev    # Local dev mode (no Docker)
"""

import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser

URL = "http://localhost:8000"
HEALTH_ENDPOINT = f"{URL}/api/health"
HEALTH_RETRIES = 30
HEALTH_DELAY = 2


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, letting stdout/stderr pass through to the terminal."""
    return subprocess.run(cmd, **kwargs)


def find_compose_cmd() -> list[str]:
    """Return the Docker Compose command as a list, or exit if not found."""
    # Try "docker compose" (v2) first, then "docker-compose" (v1)
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


def wait_for_healthy() -> bool:
    """Poll the health endpoint until it responds or we time out."""
    print("  Waiting for Maestro to start ", end="", flush=True)

    for _ in range(HEALTH_RETRIES):
        try:
            import urllib.request
            with urllib.request.urlopen(HEALTH_ENDPOINT, timeout=3) as resp:
                if resp.status == 200:
                    print(" ready!")
                    return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(HEALTH_DELAY)

    print()
    total = HEALTH_RETRIES * HEALTH_DELAY
    print(f"  Warning: Maestro did not respond within {total}s.")
    if platform.system() == "Windows":
        print("  Check logs with: docker compose logs -f")
    else:
        print("  Check logs with: make logs")
    return False


def open_browser(url: str) -> None:
    """Open the user's default browser."""
    try:
        webbrowser.open(url)
        print(f"  Browser opened to {url}")
    except Exception:
        print(f"  Open your browser to: {url}")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def docker_setup(skip_browser: bool = False) -> None:
    """Build and start the container, wait for healthy, open browser."""
    print()
    print("  +--------------------------------------+")
    print("  |    Maestro-Orchestrator Setup         |")
    print("  +--------------------------------------+")
    print()

    check_deps()

    compose = find_compose_cmd()

    print("  Building and starting container ...")
    result = run(compose + ["up", "-d", "--build"])
    if result.returncode != 0:
        print("  Error: docker compose failed. Check the output above.")
        sys.exit(1)

    print()
    if wait_for_healthy() and not skip_browser:
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
        docker_setup(skip_browser=skip_browser)


if __name__ == "__main__":
    main()
