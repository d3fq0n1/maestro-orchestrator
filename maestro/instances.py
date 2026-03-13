"""
Multi-instance management for Maestro-Orchestrator.

Provides functions to detect, spawn, stop, and query the health of
independent Maestro Docker Compose stacks running on the same host.

Each instance uses a unique Docker Compose project name (``maestro-N``)
and auto-offset ports so nothing collides:

    Instance 1: orchestrator=8000, shards=8001-8003, redis=6379, pg=5432
    Instance 2: orchestrator=8010, shards=8011-8013, redis=6380, pg=5433
    Instance 3: orchestrator=8020, shards=8021-8023, redis=6381, pg=5434
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

BASE_PORT = 8000
PORT_STRIDE = 10
PROJECT_PREFIX = "maestro"


@dataclass
class InstanceInfo:
    """Status snapshot of a single Maestro instance."""
    number: int
    project: str
    port: int
    url: str
    healthy: bool | None = None  # None = not checked yet


def project_name(n: int) -> str:
    """Docker Compose project name for instance *n* (1-based)."""
    return f"{PROJECT_PREFIX}-{n}"


def instance_port(n: int) -> int:
    """Host port for instance *n* (1-based)."""
    return BASE_PORT + (n - 1) * PORT_STRIDE


def _find_compose_cmd() -> list[str]:
    """Return the Docker Compose command as a list."""
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


def _project_root() -> str:
    """Return the project root (where docker-compose.yml lives)."""
    # Try common locations
    for candidate in [
        Path(__file__).resolve().parent.parent,
        Path.cwd(),
    ]:
        if (candidate / "docker-compose.yml").exists():
            return str(candidate)
    return str(Path.cwd())


def detect_running() -> list[int]:
    """Return sorted list of currently running instance numbers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        names = result.stdout.strip().splitlines()
        seen: set[int] = set()
        for name in names:
            for i in range(1, 100):
                if name.startswith(f"{PROJECT_PREFIX}-{i}-"):
                    seen.add(i)
                    break
        return sorted(seen)
    except Exception:
        return []


def next_instance_number() -> int:
    """Return the next available instance number."""
    running = detect_running()
    return (max(running) + 1) if running else 1


def check_health(n: int, timeout: float = 3) -> bool:
    """Return True if instance *n*'s health endpoint responds 200."""
    url = f"http://localhost:{instance_port(n)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_all_status() -> list[InstanceInfo]:
    """Return status of all running instances with health checks."""
    instances = []
    for n in detect_running():
        port = instance_port(n)
        info = InstanceInfo(
            number=n,
            project=project_name(n),
            port=port,
            url=f"http://localhost:{port}",
            healthy=check_health(n),
        )
        instances.append(info)
    return instances


def _instance_env(n: int) -> dict[str, str]:
    """Build environment dict with port offsets for instance *n*."""
    env = os.environ.copy()
    port = instance_port(n)
    offset = n - 1
    env["MAESTRO_PORT"] = str(port)
    env["REDIS_PORT"] = str(6379 + offset)
    env["POSTGRES_PORT"] = str(5432 + offset)
    env["SHARD1_PORT"] = str(port + 1)
    env["SHARD2_PORT"] = str(port + 2)
    env["SHARD3_PORT"] = str(port + 3)
    return env


def spawn(n: int | None = None, callback=None) -> InstanceInfo:
    """Spawn a new instance.  Returns its InstanceInfo.

    *n*: instance number (auto-detected if None).
    *callback*: optional ``callback(message)`` for progress updates.
    """
    if n is None:
        n = next_instance_number()

    compose = _find_compose_cmd()
    if not compose:
        raise RuntimeError("Docker Compose not found")

    proj = project_name(n)
    port = instance_port(n)
    cmd = compose + ["-p", proj]
    env = _instance_env(n)

    if callback:
        callback(f"Building {proj} on port {port}...")

    # Ensure .env exists
    root = _project_root()
    env_path = os.path.join(root, ".env")
    if not os.path.exists(env_path):
        open(env_path, "a").close()

    result = subprocess.run(
        cmd + ["up", "-d", "--build"],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start {proj}: {result.stdout[-500:] if result.stdout else 'unknown error'}"
        )

    if callback:
        callback(f"Waiting for {proj} to become healthy...")

    healthy = check_health(n, timeout=5)

    return InstanceInfo(
        number=n,
        project=proj,
        port=port,
        url=f"http://localhost:{port}",
        healthy=healthy,
    )


def stop(n: int, callback=None) -> None:
    """Stop instance *n*."""
    compose = _find_compose_cmd()
    if not compose:
        raise RuntimeError("Docker Compose not found")

    proj = project_name(n)
    if callback:
        callback(f"Stopping {proj}...")

    subprocess.run(
        compose + ["-p", proj, "down", "--remove-orphans"],
        cwd=_project_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_all(callback=None) -> int:
    """Stop all running instances.  Returns count stopped."""
    running = detect_running()
    compose = _find_compose_cmd()
    if not compose:
        return 0

    root = _project_root()
    for n in running:
        proj = project_name(n)
        if callback:
            callback(f"Stopping {proj}...")
        subprocess.run(
            compose + ["-p", proj, "down", "--remove-orphans"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Also try the default project name (legacy)
    subprocess.run(
        compose + ["down", "--remove-orphans"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return len(running)
