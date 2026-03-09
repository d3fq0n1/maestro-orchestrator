"""
API routes for the storage network and proof-of-storage system.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from maestro.shard_registry import StorageNodeRegistry, StorageNode
from maestro.storage_proof import StorageProofEngine

router = APIRouter(prefix="/api/storage", tags=["storage"])

# Shared instances (created on first use)
_registry: Optional[StorageNodeRegistry] = None
_proof_engine: Optional[StorageProofEngine] = None


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
