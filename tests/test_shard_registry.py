"""
Tests for the Shard Registry — node registration, pipeline building, redundancy.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from maestro.shard_registry import StorageNodeRegistry, StorageNode


def _make_node(node_id, host="127.0.0.1", port=8000, shards=None, **kwargs):
    return StorageNode(
        node_id=node_id,
        host=host,
        port=port,
        shards=shards or [],
        **kwargs,
    )


class TestNodeRegistration:
    def test_register_and_get(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        node = _make_node("node-1", host="10.0.0.1", port=8001)
        reg.register(node)
        retrieved = reg.get_node("node-1")
        assert retrieved is not None
        assert retrieved.host == "10.0.0.1"

    def test_unregister(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        node = _make_node("node-2")
        reg.register(node)
        assert reg.unregister("node-2")
        assert reg.get_node("node-2") is None

    def test_unregister_nonexistent(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        assert not reg.unregister("nonexistent")

    def test_list_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("a"))
        reg.register(_make_node("b"))
        reg.register(_make_node("c"))
        assert len(reg.list_nodes()) == 3

    def test_heartbeat(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("hb-node"))
        assert reg.heartbeat("hb-node")
        node = reg.get_node("hb-node")
        assert node.last_heartbeat != ""

    def test_persistence(self, tmp_path):
        reg1 = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg1.register(_make_node("persist-node", host="192.168.1.1"))

        # New registry instance loads from disk
        reg2 = StorageNodeRegistry(registry_dir=str(tmp_path))
        node = reg2.get_node("persist-node")
        assert node is not None
        assert node.host == "192.168.1.1"


class TestShardSearch:
    def _registry_with_shards(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("node-a", shards=[
            {"model_id": "llama-70b", "layer_range": [0, 15], "shard_id": "s1"},
        ]))
        reg.register(_make_node("node-b", shards=[
            {"model_id": "llama-70b", "layer_range": [16, 31], "shard_id": "s2"},
        ]))
        reg.register(_make_node("node-c", shards=[
            {"model_id": "llama-70b", "layer_range": [0, 15], "shard_id": "s3"},
            {"model_id": "mistral-7b", "layer_range": [0, 31], "shard_id": "s4"},
        ]))
        return reg

    def test_find_nodes_for_shard(self, tmp_path):
        reg = self._registry_with_shards(tmp_path)
        nodes = reg.find_nodes_for_shard("llama-70b", 0, 15)
        ids = {n.node_id for n in nodes}
        assert "node-a" in ids
        assert "node-c" in ids
        assert "node-b" not in ids

    def test_find_nodes_no_match(self, tmp_path):
        reg = self._registry_with_shards(tmp_path)
        nodes = reg.find_nodes_for_shard("nonexistent-model", 0, 10)
        assert nodes == []


class TestPipelineBuilding:
    def test_build_full_pipeline(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("p1", shards=[
            {"model_id": "llama-70b", "layer_range": [0, 15], "shard_id": "s1"},
        ], reputation_score=0.9))
        reg.register(_make_node("p2", shards=[
            {"model_id": "llama-70b", "layer_range": [16, 31], "shard_id": "s2"},
        ], reputation_score=0.9))

        pipeline = reg.build_inference_pipeline("llama-70b")
        assert len(pipeline) == 2
        assert pipeline[0].node_id == "p1"
        assert pipeline[1].node_id == "p2"

    def test_build_pipeline_prefers_reputation(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("low", shards=[
            {"model_id": "m1", "layer_range": [0, 31], "shard_id": "s1"},
        ], reputation_score=0.5))
        reg.register(_make_node("high", shards=[
            {"model_id": "m1", "layer_range": [0, 31], "shard_id": "s2"},
        ], reputation_score=0.9))

        pipeline = reg.build_inference_pipeline("m1")
        assert len(pipeline) == 1
        assert pipeline[0].node_id == "high"

    def test_build_pipeline_empty_for_missing_model(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        pipeline = reg.build_inference_pipeline("nonexistent")
        assert pipeline == []

    def test_build_pipeline_skips_offline_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("online", shards=[
            {"model_id": "m1", "layer_range": [0, 31], "shard_id": "s1"},
        ], status="available"))
        reg.register(_make_node("offline", shards=[
            {"model_id": "m1", "layer_range": [0, 31], "shard_id": "s2"},
        ], status="offline"))

        pipeline = reg.build_inference_pipeline("m1")
        assert len(pipeline) == 1
        assert pipeline[0].node_id == "online"


class TestRedundancy:
    def test_redundancy_map(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("r1", shards=[
            {"model_id": "m1", "layer_range": [0, 15], "shard_id": "s1"},
        ]))
        reg.register(_make_node("r2", shards=[
            {"model_id": "m1", "layer_range": [0, 15], "shard_id": "s2"},
        ]))
        reg.register(_make_node("r3", shards=[
            {"model_id": "m1", "layer_range": [16, 31], "shard_id": "s3"},
        ]))

        rmap = reg.get_redundancy_map("m1")
        assert "0-15" in rmap
        assert len(rmap["0-15"]) == 2
        assert "16-31" in rmap
        assert len(rmap["16-31"]) == 1


class TestStalePruning:
    def test_prune_stale_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        node = _make_node("stale-node")
        node.last_heartbeat = old.isoformat()
        reg._nodes["stale-node"] = node
        reg._save_node(node)

        pruned = reg.prune_stale_nodes(max_age_seconds=60)
        assert "stale-node" in pruned
        assert reg.get_node("stale-node") is None

    def test_prune_keeps_fresh_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("fresh-node"))  # heartbeat set to now
        pruned = reg.prune_stale_nodes(max_age_seconds=60)
        assert "fresh-node" not in pruned


class TestEmbeddingNodes:
    def test_find_embedding_nodes(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("emb-1", capabilities=["embeddings", "inference:fp16"]))
        reg.register(_make_node("inf-1", capabilities=["inference:fp16"]))
        nodes = reg.find_embedding_nodes()
        assert len(nodes) == 1
        assert nodes[0].node_id == "emb-1"


class TestReputationUpdate:
    def test_update_reputation(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("rep-node"))
        reg.update_reputation("rep-node", 0.9)
        assert reg.get_node("rep-node").reputation_score == 0.9

    def test_eviction_on_low_reputation(self, tmp_path):
        reg = StorageNodeRegistry(registry_dir=str(tmp_path))
        reg.register(_make_node("evict-node"))
        reg.update_reputation("evict-node", 0.1)
        assert reg.get_node("evict-node").status == "evicted"
