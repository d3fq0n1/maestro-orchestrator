"""
Tests for the multi-instance cluster management module.

Verifies instance name generation, port assignment, role assignment,
environment building, registry persistence, and shard topology.

Docker operations are mocked — no containers are started.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from maestro.instances import (
    BASE_PORT,
    CLUSTER_NETWORK,
    PORT_STRIDE,
    SHARED_REDIS_NAME,
    InstanceInfo,
    _all_registered,
    _cluster_shard_count,
    _instance_env,
    _load_registry,
    _register_instance,
    _save_registry,
    _unregister_instance,
    generate_instance_name,
    instance_port,
    next_instance_number,
    project_name,
)


# ---------------------------------------------------------------------------
# Name generation
# ---------------------------------------------------------------------------

class TestNameGeneration:
    def test_format(self):
        """Names should be 'adjective-animal'."""
        name = generate_instance_name()
        parts = name.split("-")
        assert len(parts) == 2
        assert all(p.isalpha() for p in parts)

    def test_randomness(self):
        """Multiple calls should produce different names (with high probability)."""
        names = {generate_instance_name() for _ in range(50)}
        # With 52 adjectives × 48 animals = 2496 combinations,
        # 50 draws should almost always produce at least 40 unique names.
        assert len(names) >= 20


# ---------------------------------------------------------------------------
# Port and project naming
# ---------------------------------------------------------------------------

class TestPortAssignment:
    def test_instance_1(self):
        assert instance_port(1) == BASE_PORT

    def test_instance_2(self):
        assert instance_port(2) == BASE_PORT + PORT_STRIDE

    def test_instance_5(self):
        assert instance_port(5) == BASE_PORT + 4 * PORT_STRIDE

    def test_project_name(self):
        assert project_name(1) == "maestro-1"
        assert project_name(3) == "maestro-3"


# ---------------------------------------------------------------------------
# Registry persistence
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_save_and_load(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )

        _save_registry({"instances": {"1": {"role": "orchestrator"}}})
        loaded = _load_registry()
        assert loaded["instances"]["1"]["role"] == "orchestrator"

    def test_register_and_unregister(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )

        _register_instance(1, {"role": "orchestrator", "human_name": "bold-eagle"})
        _register_instance(2, {"role": "shard", "shard_index": 0, "human_name": "swift-fox"})

        all_reg = _all_registered()
        assert 1 in all_reg
        assert 2 in all_reg
        assert all_reg[1]["human_name"] == "bold-eagle"
        assert all_reg[2]["shard_index"] == 0

        _unregister_instance(2)
        all_reg = _all_registered()
        assert 2 not in all_reg
        assert 1 in all_reg

    def test_load_missing_file(self, tmp_path, monkeypatch):
        reg_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        result = _load_registry()
        assert result == {"instances": {}}


# ---------------------------------------------------------------------------
# Environment building
# ---------------------------------------------------------------------------

class TestInstanceEnv:
    def test_orchestrator_env(self):
        env = _instance_env(
            n=1, role="orchestrator", shard_index=None,
            human_name="bold-eagle", total_shards=2,
        )
        assert env["NODE_ROLE"] == "orchestrator"
        assert env["NODE_ID"] == "bold-eagle"
        assert env["SHARD_COUNT"] == "2"
        assert env["MAESTRO_PORT"] == str(BASE_PORT)
        assert SHARED_REDIS_NAME in env["REDIS_URL"]
        assert "SHARD_INDEX" not in env

    def test_shard_env(self):
        env = _instance_env(
            n=2, role="shard", shard_index=0,
            human_name="swift-fox", total_shards=2,
        )
        assert env["NODE_ROLE"] == "shard"
        assert env["SHARD_INDEX"] == "0"
        assert env["SHARD_COUNT"] == "2"
        assert env["MAESTRO_PORT"] == str(BASE_PORT + PORT_STRIDE)
        assert "orchestrator" in env["ORCHESTRATOR_URL"].lower()
        assert env["MAESTRO_INSTANCE_NAME"] == "swift-fox"

    def test_shard_env_index_increments(self):
        env = _instance_env(
            n=3, role="shard", shard_index=1,
            human_name="calm-owl", total_shards=3,
        )
        assert env["SHARD_INDEX"] == "1"
        assert env["SHARD_COUNT"] == "3"


# ---------------------------------------------------------------------------
# Shard count calculation
# ---------------------------------------------------------------------------

class TestShardCount:
    def test_empty_registry(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {}})
        assert _cluster_shard_count() == 1  # minimum is 1

    def test_with_shards(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {
            "1": {"role": "orchestrator"},
            "2": {"role": "shard", "shard_index": 0},
            "3": {"role": "shard", "shard_index": 1},
        }})
        assert _cluster_shard_count() == 2


# ---------------------------------------------------------------------------
# Next instance number
# ---------------------------------------------------------------------------

class TestNextInstanceNumber:
    def test_no_running(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {}})
        monkeypatch.setattr("maestro.instances.detect_running", lambda: [])
        assert next_instance_number() == 1

    def test_with_running(self, tmp_path, monkeypatch):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {
            "1": {"role": "orchestrator"},
            "2": {"role": "shard"},
        }})
        monkeypatch.setattr("maestro.instances.detect_running", lambda: [1, 2])
        assert next_instance_number() == 3


# ---------------------------------------------------------------------------
# InstanceInfo dataclass
# ---------------------------------------------------------------------------

class TestInstanceInfo:
    def test_defaults(self):
        info = InstanceInfo(
            number=1, project="maestro-1", port=8000, url="http://localhost:8000"
        )
        assert info.role == "standalone"
        assert info.shard_index is None
        assert info.human_name == ""
        assert info.container_ip == ""

    def test_shard_instance(self):
        info = InstanceInfo(
            number=2, project="maestro-2", port=8010,
            url="http://localhost:8010",
            role="shard", shard_index=0,
            human_name="swift-fox", container_ip="172.18.0.3",
        )
        assert info.role == "shard"
        assert info.shard_index == 0
        assert info.human_name == "swift-fox"


# ---------------------------------------------------------------------------
# Spawn (mocked Docker)
# ---------------------------------------------------------------------------

class TestSpawn:
    @patch("maestro.instances.subprocess.run")
    @patch("maestro.instances._find_compose_cmd", return_value=["docker", "compose"])
    @patch("maestro.instances._project_root", return_value="/fake/root")
    @patch("maestro.instances._ensure_cluster_network")
    @patch("maestro.instances._ensure_shared_redis")
    @patch("maestro.instances._broadcast_shard_count")
    @patch("maestro.instances._get_container_ip", return_value="172.18.0.2")
    @patch("maestro.instances.check_health", return_value=True)
    @patch("maestro.instances.detect_running", return_value=[])
    @patch("os.path.exists", return_value=True)
    def test_first_spawn_is_orchestrator(
        self, mock_exists, mock_detect, mock_health, mock_ip,
        mock_broadcast, mock_redis, mock_network, mock_root,
        mock_compose, mock_run, tmp_path, monkeypatch,
    ):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {}})

        mock_run.return_value = MagicMock(returncode=0, stdout="ok")

        from maestro.instances import spawn
        info = spawn(n=1)

        assert info.role == "orchestrator"
        assert info.number == 1
        assert info.port == BASE_PORT
        assert info.healthy is True
        assert info.human_name != ""
        assert info.container_ip == "172.18.0.2"

    @patch("maestro.instances.subprocess.run")
    @patch("maestro.instances._find_compose_cmd", return_value=["docker", "compose"])
    @patch("maestro.instances._project_root", return_value="/fake/root")
    @patch("maestro.instances._ensure_cluster_network")
    @patch("maestro.instances._ensure_shared_redis")
    @patch("maestro.instances._broadcast_shard_count")
    @patch("maestro.instances._get_container_ip", return_value="172.18.0.3")
    @patch("maestro.instances.check_health", return_value=True)
    @patch("maestro.instances.detect_running", return_value=[1])
    @patch("os.path.exists", return_value=True)
    def test_second_spawn_is_shard(
        self, mock_exists, mock_detect, mock_health, mock_ip,
        mock_broadcast, mock_redis, mock_network, mock_root,
        mock_compose, mock_run, tmp_path, monkeypatch,
    ):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {
            "1": {"role": "orchestrator", "human_name": "bold-eagle"},
        }})

        mock_run.return_value = MagicMock(returncode=0, stdout="ok")

        from maestro.instances import spawn
        info = spawn(n=2)

        assert info.role == "shard"
        assert info.shard_index == 0
        assert info.number == 2
        assert info.port == BASE_PORT + PORT_STRIDE

    def test_spawn_no_docker(self, monkeypatch):
        monkeypatch.setattr(
            "maestro.instances._find_compose_cmd", lambda: []
        )
        from maestro.instances import spawn
        with pytest.raises(RuntimeError, match="Docker Compose not found"):
            spawn()


# ---------------------------------------------------------------------------
# Stop (mocked Docker)
# ---------------------------------------------------------------------------

class TestStop:
    @patch("maestro.instances.subprocess.run")
    @patch("maestro.instances._find_compose_cmd", return_value=["docker", "compose"])
    @patch("maestro.instances._project_root", return_value="/fake/root")
    @patch("maestro.instances._broadcast_shard_count")
    @patch("maestro.instances.detect_running", return_value=[])
    @patch("maestro.instances._stop_shared_redis")
    @patch("maestro.instances._cleanup_cluster_network")
    def test_stop_unregisters(
        self, mock_cleanup_net, mock_stop_redis, mock_detect,
        mock_broadcast, mock_root, mock_compose, mock_run,
        tmp_path, monkeypatch,
    ):
        reg_file = tmp_path / ".maestro-instances.json"
        monkeypatch.setattr(
            "maestro.instances._registry_path", lambda: str(reg_file)
        )
        _save_registry({"instances": {
            "1": {"role": "orchestrator", "human_name": "bold-eagle"},
        }})

        mock_run.return_value = MagicMock(returncode=0)

        from maestro.instances import stop
        stop(1)

        reg = _all_registered()
        assert 1 not in reg

    def test_stop_no_docker(self, monkeypatch):
        monkeypatch.setattr(
            "maestro.instances._find_compose_cmd", lambda: []
        )
        from maestro.instances import stop
        with pytest.raises(RuntimeError, match="Docker Compose not found"):
            stop(1)
