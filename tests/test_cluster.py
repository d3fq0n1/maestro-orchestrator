"""
Tests for the cluster module — node role detection and shard routing.
"""

import os

import pytest

from maestro.cluster import (
    ClusterConfig,
    assign_shard,
    detect_cluster_config,
    is_task_owned,
)


class TestDetectClusterConfig:
    """Test node role detection from environment variables."""

    def test_standalone_by_default(self, monkeypatch):
        monkeypatch.delenv("NODE_ROLE", raising=False)
        monkeypatch.delenv("SHARD_COUNT", raising=False)
        cfg = detect_cluster_config()
        assert cfg.role == "standalone"
        assert cfg.shard_index is None
        assert cfg.shard_count == 1

    def test_orchestrator_role(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "orchestrator")
        monkeypatch.setenv("NODE_ID", "primary")
        monkeypatch.setenv("SHARD_COUNT", "3")
        cfg = detect_cluster_config()
        assert cfg.role == "orchestrator"
        assert cfg.node_id == "primary"
        assert cfg.shard_index is None
        assert cfg.shard_count == 3

    def test_shard_role(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "shard")
        monkeypatch.setenv("NODE_ID", "shard-1")
        monkeypatch.setenv("SHARD_INDEX", "0")
        monkeypatch.setenv("SHARD_COUNT", "3")
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
        cfg = detect_cluster_config()
        assert cfg.role == "shard"
        assert cfg.node_id == "shard-1"
        assert cfg.shard_index == 0
        assert cfg.shard_count == 3
        assert cfg.orchestrator_url == "http://orchestrator:8000"

    def test_shard_with_redis(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "shard")
        monkeypatch.setenv("SHARD_INDEX", "2")
        monkeypatch.setenv("SHARD_COUNT", "4")
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
        cfg = detect_cluster_config()
        assert cfg.redis_url == "redis://redis:6379"

    def test_shard_count_1_degrades_to_standalone(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "shard")
        monkeypatch.setenv("SHARD_COUNT", "1")
        cfg = detect_cluster_config()
        assert cfg.role == "standalone"

    def test_orchestrator_with_shard_count_1(self, monkeypatch):
        """Orchestrator role is preserved even with SHARD_COUNT=1."""
        monkeypatch.setenv("NODE_ROLE", "orchestrator")
        monkeypatch.setenv("SHARD_COUNT", "1")
        cfg = detect_cluster_config()
        assert cfg.role == "orchestrator"

    def test_case_insensitive_role(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "ORCHESTRATOR")
        cfg = detect_cluster_config()
        assert cfg.role == "orchestrator"

    def test_unknown_role_treated_as_standalone(self, monkeypatch):
        monkeypatch.setenv("NODE_ROLE", "worker")
        monkeypatch.setenv("SHARD_COUNT", "3")
        cfg = detect_cluster_config()
        assert cfg.role == "standalone"


class TestShardRouting:
    """Test consistent-hash shard assignment."""

    def test_deterministic(self):
        """Same task_id always maps to the same shard."""
        for _ in range(100):
            assert assign_shard("task-abc", 3) == assign_shard("task-abc", 3)

    def test_within_range(self):
        """Shard assignment is always in [0, shard_count)."""
        for i in range(1000):
            shard = assign_shard(f"task-{i}", 5)
            assert 0 <= shard < 5

    def test_distribution(self):
        """Assignments should be roughly evenly distributed."""
        shard_count = 3
        counts = [0] * shard_count
        n = 3000
        for i in range(n):
            counts[assign_shard(f"task-{i}", shard_count)] += 1
        for c in counts:
            # Each shard should get roughly 1/3 of tasks (within 20%)
            assert c > n / shard_count * 0.6
            assert c < n / shard_count * 1.4

    def test_is_task_owned(self):
        task_id = "test-task-42"
        shard_count = 3
        owner = assign_shard(task_id, shard_count)
        assert is_task_owned(task_id, owner, shard_count)
        # Other shards should NOT own it
        for i in range(shard_count):
            if i != owner:
                assert not is_task_owned(task_id, i, shard_count)


class TestStateBus:
    """Test the state bus in disconnected (no-Redis) mode."""

    def test_disconnected_bus_safe(self):
        from maestro.state_bus import StateBus
        bus = StateBus("")  # No Redis URL
        assert not bus.connected

        # All operations should be no-ops, not raise
        bus.assign_task("t1", 0)
        assert bus.get_task("t1") is None
        bus.complete_task("t1", {"result": "ok"})
        assert bus.get_result("t1") is None
        bus.register_shard("n1", {"index": 0})
        assert bus.list_shards() == {}
        bus.publish_proof("n1", {"attestation": "abc"})
        assert bus.get_proof("n1") is None
        bus.enqueue_ledger_entry({"entry": "test"})
        assert bus.dequeue_ledger_entry() is None
        bus.set_node_health("n1", {"status": "ok"})
        assert bus.get_cluster_health() == {}
