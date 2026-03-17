"""
Multi-instance management for Maestro-Orchestrator.

Provides functions to detect, spawn, stop, and query the health of
Maestro shard/node instances running on the same host as a unified
cluster.

The first instance spawned becomes the **orchestrator** (coordinator)
along with shared infrastructure (Redis, Postgres).  Every subsequent
instance spawns as a **shard worker** that auto-registers with the
orchestrator and appears as a peer shard in the cluster.

Each instance receives:
  - A human-readable name (e.g. ``swift-falcon``)
  - A unique shard index and auto-offset host port
  - Cluster environment variables so all instances see each other

Port layout (1-based instance numbers):

    Instance 1 (orchestrator): port 8000
    Instance 2 (shard-1):      port 8010
    Instance 3 (shard-2):      port 8020
    ...
"""

from __future__ import annotations

import json
import os
import random
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_PORT = 8000
PORT_STRIDE = 10
PROJECT_PREFIX = "maestro"
CLUSTER_NETWORK = "maestro-cluster-net"
SHARED_REDIS_NAME = "maestro-shared-redis"
SHARED_REDIS_PORT = 6399   # avoid collision with per-stack redis
REGISTRY_FILE = ".maestro-instances.json"

# ---------------------------------------------------------------------------
# Human-readable name generator (matches lan_discovery.py vocabulary)
# ---------------------------------------------------------------------------

_ADJECTIVES = [
    "amber", "azure", "bold", "brave", "bright", "calm", "clear", "cool",
    "coral", "crimson", "dark", "dawn", "deep", "dusk", "eager", "fair",
    "fast", "fierce", "firm", "free", "gentle", "gilt", "grand", "gray",
    "green", "iron", "jade", "keen", "light", "lunar", "noble", "onyx",
    "pale", "prime", "quick", "rapid", "ruby", "sage", "sharp", "silver",
    "solar", "stark", "steel", "stone", "swift", "tidal", "true", "vivid",
    "warm", "wild", "wise", "zinc",
]

_ANIMALS = [
    "bear", "crane", "crow", "deer", "dove", "drake", "eagle", "elk",
    "falcon", "finch", "fox", "frog", "goat", "hare", "hawk", "heron",
    "horse", "ibis", "jay", "kite", "lark", "lion", "lynx", "mink",
    "moth", "newt", "orca", "otter", "owl", "panda", "pike", "puma",
    "ram", "raven", "robin", "seal", "shrike", "snake", "stag", "stork",
    "swan", "tiger", "toad", "viper", "whale", "wolf", "wren", "yak",
]


def generate_instance_name() -> str:
    """Generate a human-readable name like 'swift-falcon'."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_ANIMALS)}"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class InstanceInfo:
    """Status snapshot of a single Maestro instance."""
    number: int
    project: str
    port: int
    url: str
    healthy: bool | None = None   # None = not checked yet
    role: str = "standalone"      # "orchestrator" or "shard"
    shard_index: int | None = None
    human_name: str = ""
    container_ip: str = ""


# ---------------------------------------------------------------------------
# Instance registry (persisted to disk so we survive TUI restarts)
# ---------------------------------------------------------------------------

def _registry_path() -> str:
    return os.path.join(_project_root(), REGISTRY_FILE)


def _load_registry() -> dict:
    """Load the instance registry from disk."""
    path = _registry_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"instances": {}}


def _save_registry(data: dict) -> None:
    """Persist the instance registry to disk."""
    path = _registry_path()
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _register_instance(n: int, info: dict) -> None:
    """Add or update an instance in the registry."""
    reg = _load_registry()
    reg["instances"][str(n)] = info
    _save_registry(reg)


def _unregister_instance(n: int) -> None:
    """Remove an instance from the registry."""
    reg = _load_registry()
    reg["instances"].pop(str(n), None)
    _save_registry(reg)


def _get_registered(n: int) -> Optional[dict]:
    """Get registry entry for instance *n*."""
    reg = _load_registry()
    return reg["instances"].get(str(n))


def _all_registered() -> dict[int, dict]:
    """Return all registered instances as {number: info}."""
    reg = _load_registry()
    return {int(k): v for k, v in reg["instances"].items()}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

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
    for candidate in [
        Path(__file__).resolve().parent.parent,
        Path.cwd(),
    ]:
        if (candidate / "docker-compose.yml").exists():
            return str(candidate)
    return str(Path.cwd())


# ---------------------------------------------------------------------------
# Shared cluster infrastructure
# ---------------------------------------------------------------------------

def _ensure_cluster_network() -> None:
    """Create the shared Docker network if it doesn't exist."""
    try:
        result = subprocess.run(
            ["docker", "network", "inspect", CLUSTER_NETWORK],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return  # already exists
    except FileNotFoundError:
        return

    subprocess.run(
        ["docker", "network", "create", CLUSTER_NETWORK],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_port_available(port: int) -> bool:
    """Return True if *port* is free on all local interfaces."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


def _ensure_shared_redis(callback=None) -> None:
    """Start a shared Redis container on the cluster network if not running.

    Raises ``RuntimeError`` if the designated port is occupied by a process
    other than the expected shared-redis container.
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", SHARED_REDIS_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "true" in result.stdout.lower():
            return  # already running
    except Exception:
        pass

    # Before starting, verify the host port is actually available.
    if not _is_port_available(SHARED_REDIS_PORT):
        raise RuntimeError(
            f"Port {SHARED_REDIS_PORT} is already in use by another process. "
            f"Stop the process occupying port {SHARED_REDIS_PORT} or set a "
            f"different SHARED_REDIS_PORT before spawning."
        )

    if callback:
        callback("Starting shared Redis for cluster state...")

    # Remove stale container if it exists but isn't running
    subprocess.run(
        ["docker", "rm", "-f", SHARED_REDIS_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", SHARED_REDIS_NAME,
            "--network", CLUSTER_NETWORK,
            "-p", f"{SHARED_REDIS_PORT}:6379",
            "--restart", "unless-stopped",
            "redis:alpine",
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(
            f"Failed to start shared Redis container: {detail}"
        )

    # Wait briefly for Redis to accept connections
    time.sleep(1)


def _stop_shared_redis() -> None:
    """Stop and remove the shared Redis container."""
    subprocess.run(
        ["docker", "rm", "-f", SHARED_REDIS_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _cleanup_cluster_network() -> None:
    """Remove the cluster network (only if no containers are using it)."""
    subprocess.run(
        ["docker", "network", "rm", CLUSTER_NETWORK],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Detection and health
# ---------------------------------------------------------------------------

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
    registered = set(_all_registered().keys())
    all_known = set(running) | registered
    return (max(all_known) + 1) if all_known else 1


def check_health(n: int, timeout: float = 3) -> bool:
    """Return True if instance *n*'s health endpoint responds 200."""
    url = f"http://localhost:{instance_port(n)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _get_container_ip(project: str) -> str:
    """Try to resolve the container IP on the cluster network."""
    try:
        result = subprocess.run(
            [
                "docker", "inspect",
                "-f", f"{{{{.NetworkSettings.Networks.{CLUSTER_NETWORK}.IPAddress}}}}",
                f"{project}-orchestrator-1",
            ],
            capture_output=True, text=True, timeout=5,
        )
        ip = result.stdout.strip()
        if ip and ip != "<no value>":
            return ip
    except Exception:
        pass
    return ""


def get_all_status() -> list[InstanceInfo]:
    """Return status of all known instances with health checks.

    Merges both running containers (from ``docker ps``) and registry entries
    so that a freshly-spawned instance that hasn't been detected by docker-ps
    yet — or one whose container name doesn't match the detection pattern —
    still appears in the dashboard.
    """
    instances = []
    running = set(detect_running())
    registered = _all_registered()

    # Union: show every instance that is either running or registered so that
    # the TUI always reflects what was spawned, even if docker ps temporarily
    # misses it (e.g. container is still being created, or the name pattern
    # doesn't match due to a Compose v1/v2 naming difference).
    all_known = sorted(running | set(registered.keys()))

    for n in all_known:
        port = instance_port(n)
        reg = registered.get(n, {})
        info = InstanceInfo(
            number=n,
            project=project_name(n),
            port=port,
            url=f"http://localhost:{port}",
            healthy=check_health(n),
            role=reg.get("role", "orchestrator" if n == 1 else "shard"),
            shard_index=reg.get("shard_index"),
            human_name=reg.get("human_name", ""),
            container_ip=reg.get("container_ip", ""),
        )
        instances.append(info)
    return instances


# ---------------------------------------------------------------------------
# Cluster-aware environment
# ---------------------------------------------------------------------------

def _cluster_shard_count() -> int:
    """Return the total shard count based on registered instances."""
    registered = _all_registered()
    shard_count = sum(1 for v in registered.values() if v.get("role") == "shard")
    return max(1, shard_count)


def _instance_env(n: int, role: str, shard_index: int | None,
                  human_name: str, total_shards: int) -> dict[str, str]:
    """Build environment dict with cluster config for instance *n*."""
    env = os.environ.copy()
    port = instance_port(n)

    env["MAESTRO_PORT"] = str(port)
    env["COMPOSE_PROJECT_NAME"] = project_name(n)

    # Cluster identity
    env["NODE_ROLE"] = role
    env["NODE_ID"] = human_name or project_name(n)
    env["SHARD_COUNT"] = str(total_shards)
    env["MAESTRO_INSTANCE_NAME"] = human_name

    # Shared Redis on cluster network — the app connects by container name
    # on the internal 6379 port.  Do NOT set REDIS_PORT here: that variable
    # controls the *host port mapping* in docker-compose.yml and would cause
    # the per-stack redis service to collide with the shared redis container
    # that is already bound to SHARED_REDIS_PORT on the host.
    env["REDIS_URL"] = f"redis://{SHARED_REDIS_NAME}:6379"

    if role == "shard" and shard_index is not None:
        env["SHARD_INDEX"] = str(shard_index)
        env["ORCHESTRATOR_URL"] = f"http://{project_name(1)}-orchestrator-1:8000"
        env["MAESTRO_ORCHESTRATOR_URL"] = env["ORCHESTRATOR_URL"]

    # Port offsets for shard sub-services within the compose stack
    env["SHARD1_PORT"] = str(port + 1)
    env["SHARD2_PORT"] = str(port + 2)
    env["SHARD3_PORT"] = str(port + 3)
    env["POSTGRES_PORT"] = str(5432 + (n - 1))

    return env


# ---------------------------------------------------------------------------
# Spawn / Stop
# ---------------------------------------------------------------------------

def _cleanup_stale_project(proj: str, compose: list[str],
                           callback=None) -> None:
    """Tear down a stale compose project that may still hold port bindings.

    Also removes the compose-managed network for this project to prevent the
    "2 matches found based on name: network X is ambiguous" Docker error that
    occurs when a leftover network from a previous (partial) teardown causes
    Docker to find duplicate matches when the project is re-spawned.
    """
    root = _project_root()
    # Check if there are any containers (running or stopped) for this project
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={proj}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            if callback:
                callback(f"Cleaning up stale containers for {proj}...")
            subprocess.run(
                compose + ["-p", proj, "down", "--remove-orphans", "--timeout", "5"],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
    except Exception:
        pass

    # Always remove ALL compose-managed networks for this project slot, even if
    # no containers were found.  A previous partial teardown (e.g. compose down
    # that removed containers but left the network because another container was
    # transiently attached) can leave multiple stale "{proj}_maestro-net"
    # networks with the same name.  Removing by name fails when duplicates
    # exist ("2 matches found based on name: network X is ambiguous"), so we
    # enumerate by ID and remove each one individually.
    compose_network = f"{proj}_maestro-net"
    try:
        ls = subprocess.run(
            ["docker", "network", "ls", "--no-trunc",
             "--filter", f"name={compose_network}",
             "--format", "{{.ID}}\t{{.Name}}"],
            capture_output=True, text=True, timeout=10,
        )
        for line in ls.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) == 2 and parts[1] == compose_network:
                net_id = parts[0]
                if callback:
                    callback(f"Removing stale network {compose_network} ({net_id[:12]})...")
                subprocess.run(
                    ["docker", "network", "rm", net_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
    except Exception:
        pass


def _release_port(port: int, callback=None) -> None:
    """Remove any Docker container bound to *port* on the host."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"publish={port}"],
            capture_output=True, text=True, timeout=10,
        )
        container_ids = result.stdout.strip()
        if container_ids:
            if callback:
                callback(f"Removing containers bound to port {port}...")
            for cid in container_ids.splitlines():
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            # Give the OS a moment to release the socket
            time.sleep(1)
    except Exception:
        pass


def spawn(n: int | None = None, callback=None) -> InstanceInfo:
    """Spawn a new instance as a shard/node cluster member.

    The first instance becomes the orchestrator; all subsequent instances
    become shard workers that auto-register with the cluster.

    *n*: instance number (auto-detected if None).
    *callback*: optional ``callback(message)`` for progress updates.

    Returns the new InstanceInfo.
    """
    if n is None:
        n = next_instance_number()

    compose = _find_compose_cmd()
    if not compose:
        raise RuntimeError("Docker Compose not found")

    # Determine role
    running = detect_running()
    registered = _all_registered()
    is_first = (len(running) == 0 and len(registered) == 0) or n == 1

    if is_first:
        role = "orchestrator"
        shard_index = None
    else:
        role = "shard"
        # Find the next available shard index
        used_indices = {
            v.get("shard_index")
            for v in registered.values()
            if v.get("role") == "shard" and v.get("shard_index") is not None
        }
        shard_index = 0
        while shard_index in used_indices:
            shard_index += 1

    human_name = generate_instance_name()

    # Compute total shards (including this new one if it's a shard)
    current_shards = sum(
        1 for v in registered.values() if v.get("role") == "shard"
    )
    total_shards = current_shards + (1 if role == "shard" else max(1, current_shards))

    if callback:
        callback(f"Preparing cluster infrastructure...")

    # Ensure shared infrastructure
    _ensure_cluster_network()
    _ensure_shared_redis(callback=callback)

    proj = project_name(n)
    port = instance_port(n)

    # ── Pre-flight: clean up stale containers & check port ──────────
    # A previous instance may have been killed without a proper `stop`,
    # leaving a dead container that still holds the host port binding.
    # Tear down any leftover compose project for this slot first.
    _cleanup_stale_project(proj, compose, callback=callback)

    # Also kill any non-Maestro container squatting on the port.
    _release_port(port, callback=callback)

    if not _is_port_available(port):
        raise RuntimeError(
            f"Port {port} is still in use after cleanup. "
            f"Stop the process occupying port {port} before spawning instance {n}."
        )

    env = _instance_env(n, role, shard_index, human_name, total_shards)

    if callback:
        callback(f"Spawning [{human_name}] as {role} on :{port}...")

    # Ensure .env exists
    root = _project_root()
    env_path = os.path.join(root, ".env")
    if not os.path.exists(env_path):
        open(env_path, "a").close()

    # Build the compose command: run only the orchestrator service
    # (the compose file defines orchestrator + shards, but we run one
    # service per spawn and handle cluster topology ourselves).
    # --no-deps prevents Docker Compose from also starting the per-stack
    # redis/postgres services declared in depends_on — cluster mode uses
    # the shared redis container started by _ensure_shared_redis() instead.
    cmd = compose + ["-p", proj]
    services = ["orchestrator"]

    result = subprocess.run(
        cmd + ["up", "-d", "--no-deps", "--build"] + services,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start {proj}: "
            f"{result.stdout[-500:] if result.stdout else 'unknown error'}"
        )

    # Connect the container to the shared cluster network
    container_name = f"{proj}-orchestrator-1"
    subprocess.run(
        ["docker", "network", "connect", CLUSTER_NETWORK, container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if callback:
        callback(f"Waiting for [{human_name}] to become healthy...")

    # Poll for health (up to 15 seconds)
    healthy = False
    for _ in range(5):
        if check_health(n, timeout=3):
            healthy = True
            break
        time.sleep(1)

    # Resolve container IP on the cluster network
    container_ip = _get_container_ip(proj)

    # Register in our local registry
    _register_instance(n, {
        "role": role,
        "shard_index": shard_index,
        "human_name": human_name,
        "port": port,
        "container_ip": container_ip,
    })

    # Update SHARD_COUNT on all running instances so they see the new topology
    _broadcast_shard_count(callback=callback)

    return InstanceInfo(
        number=n,
        project=proj,
        port=port,
        url=f"http://localhost:{port}",
        healthy=healthy,
        role=role,
        shard_index=shard_index,
        human_name=human_name,
        container_ip=container_ip,
    )


def _broadcast_shard_count(callback=None) -> None:
    """Update the SHARD_COUNT env var on all running containers.

    This ensures every node in the cluster knows the current topology.
    Uses ``docker exec`` to write the new count into the running process'
    environment via a file that the health endpoint can read.
    """
    registered = _all_registered()
    total_shards = max(1, sum(
        1 for v in registered.values() if v.get("role") == "shard"
    ))

    # We update via the state bus (Redis) which all nodes already read.
    # If shared Redis is running, publish the topology there.
    try:
        result = subprocess.run(
            [
                "docker", "exec", SHARED_REDIS_NAME,
                "redis-cli", "SET", "maestro:cluster:shard_count", str(total_shards),
            ],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass

    # Also publish the full member list
    members = {}
    for num, info in registered.items():
        members[str(num)] = {
            "role": info.get("role"),
            "shard_index": info.get("shard_index"),
            "human_name": info.get("human_name"),
            "port": info.get("port"),
            "container_ip": info.get("container_ip", ""),
        }
    try:
        subprocess.run(
            [
                "docker", "exec", SHARED_REDIS_NAME,
                "redis-cli", "SET", "maestro:cluster:members",
                json.dumps(members),
            ],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass


def stop(n: int, callback=None) -> None:
    """Stop instance *n* and unregister it from the cluster."""
    compose = _find_compose_cmd()
    if not compose:
        raise RuntimeError("Docker Compose not found")

    proj = project_name(n)
    reg = _get_registered(n)
    name = reg.get("human_name", proj) if reg else proj

    if callback:
        callback(f"Stopping [{name}]...")

    # Disconnect from cluster network first
    container_name = f"{proj}-orchestrator-1"
    subprocess.run(
        ["docker", "network", "disconnect", CLUSTER_NETWORK, container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        compose + ["-p", proj, "down", "--remove-orphans"],
        cwd=_project_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    _unregister_instance(n)

    # Update topology for remaining nodes
    _broadcast_shard_count(callback=callback)

    # If no instances remain, clean up shared infrastructure
    if not detect_running() and not _all_registered():
        if callback:
            callback("Cleaning up shared infrastructure...")
        _stop_shared_redis()
        _cleanup_cluster_network()


def stop_all(callback=None) -> int:
    """Stop all running instances.  Returns count stopped."""
    running = detect_running()
    compose = _find_compose_cmd()
    if not compose:
        return 0

    root = _project_root()
    for n in running:
        proj = project_name(n)
        reg = _get_registered(n)
        name = reg.get("human_name", proj) if reg else proj
        if callback:
            callback(f"Stopping [{name}]...")
        subprocess.run(
            compose + ["-p", proj, "down", "--remove-orphans"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _unregister_instance(n)

    # Also try the default project name (legacy)
    subprocess.run(
        compose + ["down", "--remove-orphans"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Clean up shared infrastructure
    if callback:
        callback("Cleaning up shared infrastructure...")
    _stop_shared_redis()
    _cleanup_cluster_network()

    # Clear registry
    _save_registry({"instances": {}})

    return len(running)
