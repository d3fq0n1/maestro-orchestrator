"""
Shard Registry — Topology-aware registry of storage nodes and their weight shards.

Extends the ComputeNodeRegistry pattern to support:
  - Shard-level capability declarations (which layers of which models)
  - Pipeline construction (assembling a sequence of nodes for full inference)
  - Latency-aware routing (prefer nodes with lower round-trip times)
  - Redundancy tracking (multiple nodes can hold the same shard for failover)
  - Integration with StorageProofEngine for trust scores

Storage: data/storage_nodes/ directory, one JSON file per node.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.storage_proof import ShardDescriptor


_DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parent.parent / "data" / "storage_nodes"


@dataclass
class StorageNode:
    """A node in the proof-of-storage network."""
    node_id: str
    host: str
    port: int = 8000
    status: str = "available"        # "available", "busy", "offline", "probation", "evicted"
    shards: list = field(default_factory=list)  # list of ShardDescriptor dicts
    capabilities: list = field(default_factory=list)
    total_memory_mb: int = 0
    used_memory_mb: int = 0
    mean_latency_ms: float = 0.0
    reputation_score: float = 1.0
    metadata: dict = field(default_factory=dict)
    registered_at: str = ""
    last_heartbeat: str = ""


class StorageNodeRegistry:
    """
    Registry of storage nodes with shard-aware routing.

    Key difference from ComputeNodeRegistry: nodes are not interchangeable.
    Each node holds specific weight shards, and the registry must construct
    PIPELINES of nodes to cover all layers of a model for full inference.
    """

    def __init__(self, registry_dir: str = None):
        self._dir = Path(registry_dir) if registry_dir else _DEFAULT_REGISTRY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._nodes: dict[str, StorageNode] = {}
        self._load_nodes()

    def _load_nodes(self):
        """Load persisted node registrations from disk."""
        for filepath in self._dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text())
                node = StorageNode(**{
                    k: v for k, v in data.items()
                    if k in StorageNode.__dataclass_fields__
                })
                self._nodes[node.node_id] = node
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    def _save_node(self, node: StorageNode) -> Path:
        """Persist a node to disk."""
        filepath = self._dir / f"{node.node_id}.json"
        filepath.write_text(json.dumps(asdict(node), indent=2, default=str))
        return filepath

    def register(self, node: StorageNode) -> Path:
        """Register a new storage node or update an existing one."""
        if not node.registered_at:
            node.registered_at = datetime.now(timezone.utc).isoformat()
        node.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._nodes[node.node_id] = node
        return self._save_node(node)

    def unregister(self, node_id: str) -> bool:
        """Remove a node from the registry."""
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        filepath = self._dir / f"{node_id}.json"
        if filepath.exists():
            filepath.unlink()
        return True

    def heartbeat(self, node_id: str) -> bool:
        """Update last_heartbeat timestamp."""
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._save_node(node)
        return True

    def get_node(self, node_id: str) -> Optional[StorageNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[StorageNode]:
        """List all registered nodes."""
        return list(self._nodes.values())

    def find_nodes_for_shard(
        self,
        model_id: str,
        layer_start: int,
        layer_end: int,
    ) -> list[StorageNode]:
        """Find all nodes that hold a specific shard range."""
        matching = []
        for node in self._nodes.values():
            if node.status in ("offline", "evicted"):
                continue
            for shard in node.shards:
                shard_model = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, 'model_id', '')
                shard_range = shard.get("layer_range", []) if isinstance(shard, dict) else getattr(shard, 'layer_range', [])
                if shard_model == model_id and len(shard_range) >= 2:
                    if shard_range[0] <= layer_start and shard_range[1] >= layer_end:
                        matching.append(node)
                        break
        return matching

    def build_inference_pipeline(self, model_id: str) -> list[StorageNode]:
        """
        Construct an ordered list of nodes that together cover all layers
        of the specified model. Prefers nodes with:
          1. Higher reputation scores
          2. Lower latency
          3. Contiguous layer coverage (minimize hops)

        Returns: list[StorageNode] in layer order, or empty list if full
        coverage cannot be assembled.
        """
        # Collect all shard info for this model
        shard_nodes = []
        for node in self._nodes.values():
            if node.status in ("offline", "evicted"):
                continue
            for shard in node.shards:
                shard_model = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, 'model_id', '')
                shard_range = shard.get("layer_range", []) if isinstance(shard, dict) else getattr(shard, 'layer_range', [])
                if shard_model == model_id and len(shard_range) >= 2:
                    shard_nodes.append({
                        "node": node,
                        "start": shard_range[0],
                        "end": shard_range[1],
                    })

        if not shard_nodes:
            return []

        # Sort by start layer, then by reputation (descending) for tiebreaking
        shard_nodes.sort(key=lambda x: (x["start"], -x["node"].reputation_score))

        # Greedy pipeline construction
        pipeline = []
        current_layer = 0

        while shard_nodes:
            # Find candidates that cover the current layer
            candidates = [
                s for s in shard_nodes
                if s["start"] <= current_layer
            ]
            if not candidates:
                break  # gap in coverage

            # Pick the one that extends furthest, with best reputation as tiebreaker
            best = max(
                candidates,
                key=lambda s: (s["end"], s["node"].reputation_score, -s["node"].mean_latency_ms),
            )
            pipeline.append(best["node"])
            current_layer = best["end"] + 1
            shard_nodes.remove(best)

            # Remove candidates we passed
            shard_nodes = [s for s in shard_nodes if s["end"] >= current_layer]

        return pipeline

    def find_embedding_nodes(self, model_id: str = None) -> list[StorageNode]:
        """Find nodes capable of producing embeddings."""
        matching = []
        for node in self._nodes.values():
            if node.status in ("offline", "evicted"):
                continue
            if "embeddings" in node.capabilities:
                if model_id is None:
                    matching.append(node)
                else:
                    for shard in node.shards:
                        shard_model = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, 'model_id', '')
                        if shard_model == model_id:
                            matching.append(node)
                            break
        return matching

    def get_redundancy_map(self, model_id: str) -> dict:
        """
        Returns a dict mapping layer ranges to lists of node IDs that hold them.
        Used for failover planning and redundancy assessment.
        """
        redundancy = {}
        for node in self._nodes.values():
            if node.status in ("offline", "evicted"):
                continue
            for shard in node.shards:
                shard_model = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, 'model_id', '')
                shard_range = shard.get("layer_range", []) if isinstance(shard, dict) else getattr(shard, 'layer_range', [])
                if shard_model == model_id and len(shard_range) >= 2:
                    key = f"{shard_range[0]}-{shard_range[1]}"
                    if key not in redundancy:
                        redundancy[key] = []
                    redundancy[key].append(node.node_id)
        return redundancy

    def prune_stale_nodes(self, max_age_seconds: int = 600) -> list[str]:
        """Remove nodes that haven't sent a heartbeat within the threshold."""
        now = datetime.now(timezone.utc)
        pruned = []
        for node_id, node in list(self._nodes.items()):
            if not node.last_heartbeat:
                continue
            try:
                last = datetime.fromisoformat(node.last_heartbeat)
                if (now - last).total_seconds() > max_age_seconds:
                    self.unregister(node_id)
                    pruned.append(node_id)
            except (ValueError, TypeError):
                continue
        return pruned

    def update_reputation(self, node_id: str, score: float):
        """Update a node's reputation score (called by StorageProofEngine)."""
        node = self._nodes.get(node_id)
        if node:
            node.reputation_score = score
            if score < 0.3:
                node.status = "evicted"
            elif score < 0.7:
                node.status = "probation"
            elif node.status in ("probation", "evicted"):
                node.status = "available"
            self._save_node(node)
