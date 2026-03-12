"""
State Bus — Redis-backed shared state for multi-node Maestro clusters.

When REDIS_URL is set, state is published to and read from Redis so that
all nodes in the cluster have consistent visibility into:
  - Active task assignments  (hash: maestro:tasks)
  - Shard registration       (hash: maestro:shards)
  - Ledger entries needing cross-node consensus (list: maestro:ledger_queue)

When REDIS_URL is **not** set the bus degrades to a no-op in-process stub
so single-node deployments keep working without changes.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional


class StateBus:
    """Thin wrapper around a Redis connection for cluster state.

    All public methods are safe to call even when Redis is unavailable —
    they silently return defaults so callers never need to check.
    """

    def __init__(self, redis_url: str = ""):
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "")
        self._redis = None
        if self._redis_url:
            self._connect()

    def _connect(self):
        try:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Verify connectivity
            self._redis.ping()
        except Exception as e:
            print(f"[StateBus] Redis connection failed ({self._redis_url}): {e}")
            self._redis = None

    @property
    def connected(self) -> bool:
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    # ── Task assignments ─────────────────────────────────────────────

    def assign_task(self, task_id: str, shard_index: int, meta: dict = None):
        """Record a task assignment in the shared bus."""
        if not self._redis:
            return
        payload = json.dumps({
            "shard_index": shard_index,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            **(meta or {}),
        })
        try:
            self._redis.hset("maestro:tasks", task_id, payload)
        except Exception:
            pass

    def get_task(self, task_id: str) -> Optional[dict]:
        if not self._redis:
            return None
        try:
            raw = self._redis.hget("maestro:tasks", task_id)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def complete_task(self, task_id: str, result: dict):
        """Mark a task as completed and store its result."""
        if not self._redis:
            return
        try:
            payload = json.dumps({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            })
            self._redis.hset("maestro:results", task_id, payload)
            self._redis.hdel("maestro:tasks", task_id)
        except Exception:
            pass

    def get_result(self, task_id: str) -> Optional[dict]:
        if not self._redis:
            return None
        try:
            raw = self._redis.hget("maestro:results", task_id)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    # ── Shard registration ───────────────────────────────────────────

    def register_shard(self, node_id: str, shard_info: dict):
        """Announce this shard node's identity to the cluster."""
        if not self._redis:
            return
        try:
            payload = json.dumps({
                "node_id": node_id,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                **shard_info,
            })
            self._redis.hset("maestro:shards", node_id, payload)
        except Exception:
            pass

    def list_shards(self) -> dict[str, dict]:
        """Return all registered shard nodes."""
        if not self._redis:
            return {}
        try:
            raw = self._redis.hgetall("maestro:shards")
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception:
            return {}

    def unregister_shard(self, node_id: str):
        if not self._redis:
            return
        try:
            self._redis.hdel("maestro:shards", node_id)
        except Exception:
            pass

    # ── Storage proofs ───────────────────────────────────────────────

    def publish_proof(self, node_id: str, proof: dict):
        """Publish a storage proof attestation."""
        if not self._redis:
            return
        try:
            payload = json.dumps({
                "node_id": node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **proof,
            })
            self._redis.hset("maestro:proofs", node_id, payload)
        except Exception:
            pass

    def get_proof(self, node_id: str) -> Optional[dict]:
        if not self._redis:
            return None
        try:
            raw = self._redis.hget("maestro:proofs", node_id)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    # ── Ledger consensus queue ───────────────────────────────────────

    def enqueue_ledger_entry(self, entry: dict):
        """Push a ledger entry that needs cross-node consensus."""
        if not self._redis:
            return
        try:
            self._redis.rpush("maestro:ledger_queue", json.dumps(entry))
        except Exception:
            pass

    def dequeue_ledger_entry(self) -> Optional[dict]:
        if not self._redis:
            return None
        try:
            raw = self._redis.lpop("maestro:ledger_queue")
            return json.loads(raw) if raw else None
        except Exception:
            return None

    # ── Health / cluster info ────────────────────────────────────────

    def set_node_health(self, node_id: str, health: dict):
        """Update this node's health record."""
        if not self._redis:
            return
        try:
            payload = json.dumps({
                "node_id": node_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **health,
            })
            self._redis.hset("maestro:health", node_id, payload)
            self._redis.expire("maestro:health", 120)  # auto-expire stale entries
        except Exception:
            pass

    def get_cluster_health(self) -> dict[str, dict]:
        if not self._redis:
            return {}
        try:
            raw = self._redis.hgetall("maestro:health")
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception:
            return {}


# ── Module-level singleton ───────────────────────────────────────────

_bus: Optional[StateBus] = None


def get_state_bus() -> StateBus:
    global _bus
    if _bus is None:
        _bus = StateBus()
    return _bus
