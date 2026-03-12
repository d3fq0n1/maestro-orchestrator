"""
Cluster — Node role detection and consistent-hash shard routing.

Reads environment variables to determine whether this Maestro instance
is running as an orchestrator (coordinator-of-coordinators) or as a
shard worker node.  When SHARD_COUNT is 1 or NODE_ROLE is unset the
system behaves identically to the original single-process architecture.

Environment variables:
    NODE_ROLE      — "orchestrator" or "shard" (default: single-node)
    NODE_ID        — unique identifier for this instance
    SHARD_INDEX    — 0-based position in the shard ring (shard nodes only)
    SHARD_COUNT    — total number of shard nodes in the cluster
    ORCHESTRATOR_URL — URL of the orchestrator (shard nodes only)
    REDIS_URL      — optional Redis connection for the shared state bus
"""

import hashlib
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ClusterConfig:
    """Immutable snapshot of this node's cluster identity."""
    role: str                       # "orchestrator", "shard", or "standalone"
    node_id: str
    shard_index: Optional[int]      # None for orchestrator / standalone
    shard_count: int
    orchestrator_url: str           # empty for orchestrator / standalone
    redis_url: str                  # empty when Redis is not configured


def detect_cluster_config() -> ClusterConfig:
    """Read cluster identity from the environment.

    Falls back to standalone mode when NODE_ROLE is unset or
    SHARD_COUNT <= 1.
    """
    role_raw = os.environ.get("NODE_ROLE", "").lower().strip()
    node_id = os.environ.get("NODE_ID", "standalone")
    shard_count = int(os.environ.get("SHARD_COUNT", "1"))
    shard_index_raw = os.environ.get("SHARD_INDEX")
    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "")
    redis_url = os.environ.get("REDIS_URL", "")

    # Determine effective role
    if role_raw == "orchestrator":
        role = "orchestrator"
        shard_index = None
    elif role_raw == "shard":
        role = "shard"
        shard_index = int(shard_index_raw) if shard_index_raw is not None else 0
    else:
        # No role set — single-node mode
        role = "standalone"
        shard_index = None

    # Single shard count degrades gracefully to standalone behaviour
    if shard_count <= 1 and role != "orchestrator":
        role = "standalone"

    return ClusterConfig(
        role=role,
        node_id=node_id,
        shard_index=shard_index,
        shard_count=max(1, shard_count),
        orchestrator_url=orchestrator_url,
        redis_url=redis_url,
    )


# ── Consistent-hash shard routing ────────────────────────────────────

def assign_shard(task_id: str, shard_count: int) -> int:
    """Deterministically map a task ID to a shard index via SHA-256.

    >>> assign_shard("task-abc", 3) in (0, 1, 2)
    True
    """
    h = int(hashlib.sha256(task_id.encode()).hexdigest(), 16)
    return h % shard_count


def is_task_owned(task_id: str, shard_index: int, shard_count: int) -> bool:
    """Return True if *task_id* belongs to *shard_index*."""
    return assign_shard(task_id, shard_count) == shard_index


# ── Module-level singleton ───────────────────────────────────────────

_config: Optional[ClusterConfig] = None


def get_cluster_config() -> ClusterConfig:
    """Return (and cache) the cluster configuration."""
    global _config
    if _config is None:
        _config = detect_cluster_config()
    return _config


def is_standalone() -> bool:
    return get_cluster_config().role == "standalone"


def is_orchestrator() -> bool:
    return get_cluster_config().role == "orchestrator"


def is_shard() -> bool:
    return get_cluster_config().role == "shard"
