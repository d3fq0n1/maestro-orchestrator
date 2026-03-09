"""
Tests for ShardAgent — distributed inference via mocked nodes.
"""

import asyncio
import json

import pytest

from maestro.agents.shard import ShardAgent
from maestro.agents.mock_shard_node import MockShardNode
from maestro.shard_registry import StorageNodeRegistry, StorageNode
from maestro.storage_proof import StorageProofEngine, NodeReputation


class TestShardAgentBasic:
    def test_no_registry_returns_error(self):
        agent = ShardAgent(registry=None)
        result = asyncio.run(agent.fetch("hello"))
        assert "[ShardNet]" in result
        assert "No storage registry" in result

    def test_no_nodes_returns_error(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        agent = ShardAgent(registry=reg)
        result = asyncio.run(agent.fetch("hello"))
        assert "[ShardNet]" in result
        assert "No storage nodes" in result

    def test_name_and_model(self):
        agent = ShardAgent(model_id="test-model")
        assert agent.name == "ShardNet"
        assert agent.model == "test-model"


class TestShardAgentWithMocks:
    def _setup(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(StorageNode(
            node_id="mock-node",
            host="127.0.0.1",
            port=9999,
            shards=[{"model_id": "test-model", "layer_range": [0, 31], "shard_id": "s1"}],
            reputation_score=1.0,
        ))
        return reg

    def test_reputation_filter_removes_low_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(StorageNode(
            node_id="low-rep",
            host="127.0.0.1",
            port=9999,
            shards=[{"model_id": "test-model", "layer_range": [0, 31], "shard_id": "s1"}],
            reputation_score=0.2,
        ))

        proof = StorageProofEngine(proof_dir=str(tmp_path / "proofs"))
        proof._reputations["low-rep"] = NodeReputation(
            node_id="low-rep", reputation_score=0.2,
        )

        agent = ShardAgent(
            model_id="test-model",
            registry=reg,
            proof_engine=proof,
            min_reputation=0.5,
        )
        result = asyncio.run(agent.fetch("test prompt"))
        assert "No trusted nodes" in result


class TestMockShardNode:
    def test_handle_infer(self):
        node = MockShardNode("mock-1", "llama-70b", (0, 15))
        result = asyncio.run(node.handle_infer({
            "session_id": "test",
            "model_id": "llama-70b",
            "prompt": "hello world",
            "sequence_length": 2,
            "hidden_dim": 4096,
            "dtype": "float16",
        }))
        assert result["layer_completed"] == 15
        assert result["decoded_text"] != ""
        assert "mock-1" in result["metadata"]["source_node"]

    def test_handle_challenge(self):
        node = MockShardNode("mock-1", "llama-70b", (0, 15))
        result = asyncio.run(node.handle_challenge({
            "challenge_id": "test-challenge",
            "expected_hash": "abc123",
        }))
        assert result["passed"] is True
        assert result["response_hash"] == "abc123"

    def test_health(self):
        node = MockShardNode("mock-1", "llama-70b", (0, 15))
        h = node.health()
        assert h["node_id"] == "mock-1"
        assert h["status"] == "available"
