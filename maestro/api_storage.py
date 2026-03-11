"""
API routes for the storage network and proof-of-storage system.

Covers two concerns:
  1. Network management — nodes, reputation, pipelines, challenges
  2. Shard management — download, index, verify local weight shards
"""

import asyncio
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional

from maestro.shard_registry import StorageNodeRegistry, StorageNode
from maestro.storage_proof import StorageProofEngine
from maestro.shard_manager import ShardManager
from maestro.lan_discovery import ShardDiscoveryEngine

router = APIRouter(prefix="/api/storage", tags=["storage"])

# Shared instances (created on first use)
_registry: Optional[StorageNodeRegistry] = None
_proof_engine: Optional[StorageProofEngine] = None
_shard_manager: Optional[ShardManager] = None
_discovery_engine: Optional[ShardDiscoveryEngine] = None

# Track in-progress downloads
_active_downloads: dict[str, dict] = {}


def _get_registry() -> StorageNodeRegistry:
    global _registry
    if _registry is None:
        _registry = StorageNodeRegistry()
    return _registry


def _get_proof_engine() -> StorageProofEngine:
    global _proof_engine
    if _proof_engine is None:
        _proof_engine = StorageProofEngine()
    return _proof_engine


def _get_shard_manager() -> ShardManager:
    global _shard_manager
    if _shard_manager is None:
        _shard_manager = ShardManager()
    return _shard_manager


async def _get_discovery_engine() -> ShardDiscoveryEngine:
    global _discovery_engine
    if _discovery_engine is None:
        _discovery_engine = ShardDiscoveryEngine()
        await _discovery_engine.start()
    return _discovery_engine


# --- Request models ---

class NodeRegistration(BaseModel):
    node_id: str
    host: str
    port: int = 8000
    shards: list = Field(default_factory=list)
    capabilities: list = Field(default_factory=list)
    total_memory_mb: int = 0


class ChallengeRequest(BaseModel):
    challenge_type: str = "byte_range_hash"
    shard_id: str = ""


class ShardDownloadRequest(BaseModel):
    model_id: str
    layer_start: int = 0
    layer_end: int = -1
    token: str = ""


class GenerateConfigRequest(BaseModel):
    model_id: str
    layer_start: Optional[int] = None
    layer_end: Optional[int] = None
    output_path: str = "data/node_shards.json"


# --- Endpoints ---

@router.post("/nodes/register")
async def register_node(reg: NodeRegistration):
    registry = _get_registry()
    node = StorageNode(
        node_id=reg.node_id,
        host=reg.host,
        port=reg.port,
        shards=reg.shards,
        capabilities=reg.capabilities,
        total_memory_mb=reg.total_memory_mb,
    )
    registry.register(node)
    return {"status": "registered", "node_id": node.node_id}


@router.delete("/nodes/{node_id}")
async def unregister_node(node_id: str):
    registry = _get_registry()
    if registry.unregister(node_id):
        return {"status": "unregistered", "node_id": node_id}
    raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")


@router.get("/nodes")
async def list_nodes():
    registry = _get_registry()
    nodes = registry.list_nodes()
    return {
        "count": len(nodes),
        "nodes": [
            {
                "node_id": n.node_id,
                "host": n.host,
                "port": n.port,
                "status": n.status,
                "shards": n.shards,
                "capabilities": n.capabilities,
                "reputation_score": n.reputation_score,
                "mean_latency_ms": n.mean_latency_ms,
                "last_heartbeat": n.last_heartbeat,
            }
            for n in nodes
        ],
    }


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    registry = _get_registry()
    node = registry.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    engine = _get_proof_engine()
    rep = engine.get_reputation(node_id)
    return {
        "node_id": node.node_id,
        "host": node.host,
        "port": node.port,
        "status": node.status,
        "shards": node.shards,
        "capabilities": node.capabilities,
        "reputation": {
            "score": rep.reputation_score,
            "status": rep.status,
            "challenges_issued": rep.challenges_issued,
            "challenges_passed": rep.challenges_passed,
            "challenges_failed": rep.challenges_failed,
            "pass_rate": rep.challenge_pass_rate,
        },
        "mean_latency_ms": node.mean_latency_ms,
        "last_heartbeat": node.last_heartbeat,
    }


@router.post("/challenge/{node_id}")
async def trigger_challenge(node_id: str, req: ChallengeRequest):
    engine = _get_proof_engine()
    shard_id = req.shard_id or "default"
    challenge = engine.issue_challenge(node_id, shard_id, req.challenge_type)
    return {
        "challenge_id": challenge.challenge_id,
        "node_id": node_id,
        "type": challenge.challenge_type,
        "expires_at": challenge.expires_at,
    }


@router.get("/pipeline/{model_id:path}")
async def get_pipeline(model_id: str):
    registry = _get_registry()
    pipeline = registry.build_inference_pipeline(model_id)
    return {
        "model_id": model_id,
        "hops": len(pipeline),
        "pipeline": [
            {"node_id": n.node_id, "host": n.host, "port": n.port}
            for n in pipeline
        ],
    }


@router.get("/redundancy/{model_id:path}")
async def get_redundancy(model_id: str):
    registry = _get_registry()
    return {
        "model_id": model_id,
        "redundancy_map": registry.get_redundancy_map(model_id),
    }


@router.get("/reputation")
async def all_reputations():
    engine = _get_proof_engine()
    return {"reputations": engine.list_reputations()}


@router.get("/network/topology")
async def network_topology():
    """Full network topology: nodes, their shards, per-model coverage, and mirror status."""
    registry = _get_registry()
    engine = _get_proof_engine()
    nodes = registry.list_nodes()

    # Collect all model IDs across the network
    model_ids: set[str] = set()
    for node in nodes:
        for shard in node.shards:
            mid = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, "model_id", "")
            if mid:
                model_ids.add(mid)

    # Per-model: compute coverage, redundancy, pipeline, and mirror status
    models = []
    for model_id in sorted(model_ids):
        redundancy = registry.get_redundancy_map(model_id)
        pipeline = registry.build_inference_pipeline(model_id)

        # Compute total layer coverage across all nodes
        all_layers: set[int] = set()
        node_contributions: list[dict] = []
        for node in nodes:
            if node.status in ("offline", "evicted"):
                continue
            for shard in node.shards:
                s_model = shard.get("model_id", "") if isinstance(shard, dict) else getattr(shard, "model_id", "")
                s_range = shard.get("layer_range", []) if isinstance(shard, dict) else getattr(shard, "layer_range", [])
                if s_model == model_id and len(s_range) >= 2:
                    for layer in range(s_range[0], s_range[1] + 1):
                        all_layers.add(layer)
                    node_contributions.append({
                        "node_id": node.node_id,
                        "layer_range": list(s_range[:2]),
                        "reputation": node.reputation_score,
                        "latency_ms": node.mean_latency_ms,
                        "status": node.status,
                    })

        # Determine if layers form a complete mirror (contiguous from 0)
        total_layers = (max(all_layers) + 1) if all_layers else 0
        covered_count = len(all_layers)
        coverage_pct = round(covered_count / total_layers * 100, 1) if total_layers > 0 else 0
        is_mirror = (
            total_layers > 0
            and covered_count == total_layers
            and min(all_layers) == 0
        )

        # Build sorted coverage ranges
        coverage_ranges = []
        if all_layers:
            sorted_layers = sorted(all_layers)
            start = sorted_layers[0]
            prev = start
            for layer in sorted_layers[1:]:
                if layer != prev + 1:
                    coverage_ranges.append([start, prev])
                    start = layer
                prev = layer
            coverage_ranges.append([start, prev])

        # Identify gaps
        gaps = []
        if all_layers and total_layers > 0:
            for i in range(total_layers):
                if i not in all_layers:
                    if not gaps or gaps[-1][1] != i - 1:
                        gaps.append([i, i])
                    else:
                        gaps[-1][1] = i

        models.append({
            "model_id": model_id,
            "total_layers": total_layers,
            "covered_layers": covered_count,
            "coverage_pct": coverage_pct,
            "coverage_ranges": coverage_ranges,
            "gaps": gaps,
            "is_mirror": is_mirror,
            "pipeline_hops": len(pipeline),
            "pipeline": [{"node_id": n.node_id, "host": n.host, "port": n.port} for n in pipeline],
            "redundancy_map": redundancy,
            "node_contributions": node_contributions,
        })

    # Node summary with reputation details
    node_list = []
    for node in nodes:
        rep = engine.get_reputation(node.node_id)
        node_list.append({
            "node_id": node.node_id,
            "host": node.host,
            "port": node.port,
            "status": node.status,
            "reputation_score": node.reputation_score,
            "reputation_status": rep.status,
            "mean_latency_ms": node.mean_latency_ms,
            "shard_count": len(node.shards),
            "shards": node.shards,
            "capabilities": node.capabilities,
            "last_heartbeat": node.last_heartbeat,
        })

    return {
        "node_count": len(nodes),
        "model_count": len(models),
        "nodes": node_list,
        "models": models,
    }


# --- Shard management endpoints ---

@router.get("/shards/models")
async def list_shard_models():
    """List all models with local shards."""
    manager = _get_shard_manager()
    models = manager.list_models()
    results = []
    for model_id in models:
        manifest = manager.load_manifest(model_id)
        usage = manager.disk_usage(model_id)
        results.append({
            "model_id": model_id,
            "total_layers": manifest.total_layers if manifest else 0,
            "layer_coverage": manifest.layer_coverage if manifest else [],
            "complete": manifest.complete if manifest else False,
            "precision": manifest.precision if manifest else "",
            "files": usage.get("files", 0),
            "total_gb": usage.get("total_gb", 0),
        })
    return {"models": results}


@router.get("/shards/status/{model_id:path}")
async def shard_status(model_id: str):
    """Get detailed shard status for a model."""
    manager = _get_shard_manager()
    manifest = manager.load_manifest(model_id)
    if not manifest:
        # Try indexing
        manifest = manager.index_shards(model_id)
    usage = manager.disk_usage(model_id)
    downloading = _active_downloads.get(model_id)
    return {
        "model_id": model_id,
        "total_layers": manifest.total_layers,
        "layer_coverage": manifest.layer_coverage,
        "complete": manifest.complete,
        "precision": manifest.precision,
        "files": manifest.files,
        "total_size_bytes": manifest.total_size_bytes,
        "total_gb": usage.get("total_gb", 0),
        "downloading": downloading is not None,
        "download_status": downloading,
    }


@router.post("/shards/download")
async def download_shards(req: ShardDownloadRequest, background_tasks: BackgroundTasks):
    """Start downloading shards for a model (runs in background)."""
    model_id = req.model_id
    if model_id in _active_downloads:
        return {"status": "already_downloading", "model_id": model_id}

    _active_downloads[model_id] = {"status": "starting", "model_id": model_id}

    def _do_download():
        try:
            _active_downloads[model_id] = {
                "status": "downloading",
                "model_id": model_id,
                "layer_start": req.layer_start,
                "layer_end": req.layer_end,
            }
            manager = _get_shard_manager()
            downloaded = manager.download_model_shards(
                model_id=model_id,
                layer_start=req.layer_start,
                layer_end=req.layer_end,
                token=req.token or None,
            )
            _active_downloads[model_id] = {
                "status": "complete",
                "model_id": model_id,
                "files_downloaded": len(downloaded),
            }
        except Exception as e:
            _active_downloads[model_id] = {
                "status": "error",
                "model_id": model_id,
                "error": str(e),
            }

    background_tasks.add_task(_do_download)
    return {"status": "started", "model_id": model_id}


@router.get("/shards/download-status/{model_id:path}")
async def download_status(model_id: str):
    """Check download status for a model."""
    status = _active_downloads.get(model_id)
    if not status:
        return {"status": "idle", "model_id": model_id}
    return status


@router.delete("/shards/download-status/{model_id:path}")
async def clear_download_status(model_id: str):
    """Clear completed/errored download status."""
    _active_downloads.pop(model_id, None)
    return {"status": "cleared", "model_id": model_id}


@router.post("/shards/verify/{model_id:path}")
async def verify_shards(model_id: str):
    """Verify integrity of local shards for a model."""
    manager = _get_shard_manager()
    results = manager.verify_all(model_id)
    return {"model_id": model_id, **results}


@router.get("/shards/disk-usage")
async def shard_disk_usage():
    """Get disk usage for all local shards."""
    manager = _get_shard_manager()
    return manager.disk_usage()


@router.delete("/shards/{model_id:path}")
async def remove_model_shards(model_id: str):
    """Remove all local shards for a model."""
    manager = _get_shard_manager()
    if manager.remove_model(model_id):
        return {"status": "removed", "model_id": model_id}
    raise HTTPException(status_code=404, detail=f"No shards found for: {model_id}")


@router.post("/shards/generate-config")
async def generate_shard_config(req: GenerateConfigRequest):
    """Generate a node_shards.json config from local shards."""
    manager = _get_shard_manager()
    config = manager.generate_shard_config(
        model_id=req.model_id,
        layer_start=req.layer_start,
        layer_end=req.layer_end,
        output_path=req.output_path,
    )
    return {
        "status": "generated",
        "model_id": req.model_id,
        "output_path": req.output_path,
        "shard_count": len(config),
        "shards": config,
    }


# --- LAN Discovery endpoints ---

@router.get("/discovery")
async def discovery_status():
    """Get LAN shard discovery status: identity, peers, adjacencies, node formation."""
    engine = await _get_discovery_engine()
    return engine.snapshot()


@router.get("/discovery/peers")
async def discovery_peers():
    """List discovered peers with adjacency state."""
    engine = await _get_discovery_engine()
    return {"peers": engine.peer_summary()}


@router.get("/discovery/node")
async def discovery_node_status():
    """Get Maestro Node formation status."""
    engine = await _get_discovery_engine()
    return engine.node_status.to_dict()
