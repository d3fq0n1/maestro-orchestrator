"""
Weight Host Registry — Topology-aware registry of persistent weight hosts.

Each WeightHost is a node in the distributed inference mesh that holds model
weight shards persistently. Queries travel to weights, not weights to queries.

Supports:
  - Shard-level capability declarations (which layers of which models)
  - Capability manifests (domain affinity, warmth, hardware class)
  - Locality-aware routing (prefer warm hosts with matching domain affinity)
  - Pipeline construction (assembling a sequence of hosts for full inference)
  - Latency-aware routing (prefer hosts with lower round-trip times)
  - Redundancy tracking (multiple hosts can hold the same shard for failover)
  - Integration with StorageProofEngine for trust scores

Storage: data/storage_nodes/ directory, one JSON file per host.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.storage_proof import ShardDescriptor


_DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parent.parent / "data" / "storage_nodes"


# Hardware classification for weight hosts
HARDWARE_CLASSES = ("cloud_api", "local_gpu", "edge_node", "unknown")


@dataclass
class WeightHost:
    """A persistent weight host in the distributed inference mesh.

    Each WeightHost holds model weight shards and declares a capability
    profile that the orchestrator uses for locality-aware routing.
    """
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

    # --- Capability manifest ---
    # These fields are the foundation for locality-aware routing.
    domain_affinity: list = field(default_factory=list)  # query types this host handles well
    warm: bool = False                                    # whether this host has been recently active
    hardware_class: str = "unknown"                       # one of HARDWARE_CLASSES
    last_active: str = ""                                 # ISO timestamp of last inference activity


# Backward-compatible alias — existing serialized state and external code
# that references StorageNode continues to work.
StorageNode = WeightHost


def weight_locality_score(
    host: "WeightHost",
    query_domains: list[str] | None = None,
) -> float:
    """Compute a locality score for routing decisions.

    The score captures how well-positioned a host is to serve a query
    right now, combining warmth and domain affinity into a single
    comparable value.

    Routing preference order (encoded in the score):
      1. Warm host with matching domain affinity  -> 1.0
      2. Warm host, any affinity                  -> 0.75
      3. Cold host with matching domain affinity   -> 0.5
      4. Cold host, any affinity                   -> 0.25

    This score is a named factor in the routing decision path — it
    participates alongside reputation and latency in every pipeline
    construction and host selection call.
    """
    query_domains = query_domains or []

    has_affinity = bool(
        query_domains
        and host.domain_affinity
        and any(d in host.domain_affinity for d in query_domains)
    )

    if host.warm and has_affinity:
        return 1.0
    if host.warm:
        return 0.75
    if has_affinity:
        return 0.5
    return 0.25


class WeightHostRegistry:
    """
    Registry of persistent weight hosts with locality-aware routing.

    Each host holds specific weight shards. The registry constructs
    inference pipelines across hosts, preferring warm hosts with
    matching domain affinity — routing queries to where the weights
    already live.
    """

    def __init__(self, registry_dir: str = None):
        self._dir = Path(registry_dir) if registry_dir else _DEFAULT_REGISTRY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._nodes: dict[str, WeightHost] = {}
        self._load_nodes()

    def _load_nodes(self):
        """Load persisted host registrations from disk."""
        for filepath in self._dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text())
                node = WeightHost(**{
                    k: v for k, v in data.items()
                    if k in WeightHost.__dataclass_fields__
                })
                self._nodes[node.node_id] = node
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    def _save_node(self, node: WeightHost) -> Path:
        """Persist a host to disk."""
        filepath = self._dir / f"{node.node_id}.json"
        filepath.write_text(json.dumps(asdict(node), indent=2, default=str))
        return filepath

    def register(self, node: WeightHost) -> Path:
        """Register a new weight host or update an existing one."""
        if not node.registered_at:
            node.registered_at = datetime.now(timezone.utc).isoformat()
        node.last_heartbeat = datetime.now(timezone.utc).isoformat()
        # Validate hardware_class
        if node.hardware_class not in HARDWARE_CLASSES:
            node.hardware_class = "unknown"
        self._nodes[node.node_id] = node
        return self._save_node(node)

    def unregister(self, node_id: str) -> bool:
        """Remove a host from the registry."""
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

    def mark_active(self, node_id: str) -> bool:
        """Mark a host as warm and update its last_active timestamp.

        Called after a host successfully serves an inference request.
        """
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.warm = True
        node.last_active = datetime.now(timezone.utc).isoformat()
        self._save_node(node)
        return True

    def get_node(self, node_id: str) -> Optional[WeightHost]:
        """Get a host by ID."""
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[WeightHost]:
        """List all registered hosts."""
        return list(self._nodes.values())

    def find_nodes_for_shard(
        self,
        model_id: str,
        layer_start: int,
        layer_end: int,
    ) -> list[WeightHost]:
        """Find all hosts that hold a specific shard range."""
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

    def route_query(
        self,
        model_id: str,
        query_domains: list[str] | None = None,
    ) -> list[WeightHost]:
        """Route a query to the best available weight hosts.

        This is the primary routing entry point. It constructs an inference
        pipeline using weight_locality_score as a first-class routing factor
        alongside reputation and latency.

        Preference order:
          1. Warm host with matching domain affinity
          2. Warm host, any affinity
          3. Cold host with matching domain affinity
          4. Cold host, any affinity
        """
        return self.build_inference_pipeline(
            model_id, query_domains=query_domains,
        )

    def build_inference_pipeline(
        self,
        model_id: str,
        query_domains: list[str] | None = None,
    ) -> list[WeightHost]:
        """
        Construct an ordered list of hosts that together cover all layers
        of the specified model. Prefers hosts with:
          1. Higher weight_locality_score (warm + domain affinity)
          2. Higher reputation scores
          3. Lower latency
          4. Contiguous layer coverage (minimize hops)

        Returns: list[WeightHost] in layer order, or empty list if full
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
                    locality = weight_locality_score(node, query_domains)
                    shard_nodes.append({
                        "node": node,
                        "start": shard_range[0],
                        "end": shard_range[1],
                        "locality": locality,
                    })

        if not shard_nodes:
            return []

        # Sort by start layer, then by locality (descending), then reputation
        shard_nodes.sort(key=lambda x: (
            x["start"],
            -x["locality"],
            -x["node"].reputation_score,
        ))

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

            # Pick the one that extends furthest, weighted by locality + reputation
            best = max(
                candidates,
                key=lambda s: (
                    s["end"],
                    s["locality"],
                    s["node"].reputation_score,
                    -s["node"].mean_latency_ms,
                ),
            )
            pipeline.append(best["node"])
            current_layer = best["end"] + 1
            shard_nodes.remove(best)

            # Remove candidates we passed
            shard_nodes = [s for s in shard_nodes if s["end"] >= current_layer]

        return pipeline

    def find_embedding_nodes(self, model_id: str = None) -> list[WeightHost]:
        """Find hosts capable of producing embeddings."""
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
        Returns a dict mapping layer ranges to lists of host IDs that hold them.
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
        """Remove hosts that haven't sent a heartbeat within the threshold."""
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
        """Update a host's reputation score (called by StorageProofEngine)."""
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


# Backward-compatible alias
StorageNodeRegistry = WeightHostRegistry
