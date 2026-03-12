"""
API routes for the cluster orchestrator.

Provides endpoints that the orchestrator uses to:
  - Dispatch tasks to shard nodes via consistent hashing
  - Collect results from shard nodes
  - Run storage proof challenges against all shards
  - View cluster health and topology
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maestro.cluster import (
    get_cluster_config,
    assign_shard,
    is_orchestrator,
    is_standalone,
)
from maestro.state_bus import get_state_bus

router = APIRouter(prefix="/api/cluster", tags=["cluster"])


# ── Request/Response models ──────────────────────────────────────────

class DispatchRequest(BaseModel):
    prompt: str
    task_id: str = ""
    metadata: dict = Field(default_factory=dict)


class ProofChallengeRequest(BaseModel):
    nonce: str = ""


# ── Shard URL resolution ────────────────────────────────────────────

def _shard_urls() -> dict[int, str]:
    """Build a mapping of shard_index -> base URL from the state bus
    or fall back to Docker Compose service naming convention.
    """
    cfg = get_cluster_config()
    bus = get_state_bus()

    # Try Redis first
    shards = bus.list_shards()
    if shards:
        urls = {}
        for node_id, info in shards.items():
            idx = info.get("shard_index")
            if idx is not None:
                # Use Docker service name (node_id is the service name)
                urls[idx] = f"http://{node_id}:8000"
        if urls:
            return urls

    # Fallback: Docker Compose naming convention
    return {
        i: f"http://shard-{i + 1}:8000"
        for i in range(cfg.shard_count)
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/status")
async def cluster_status():
    """Cluster overview: role, shard count, connected nodes."""
    cfg = get_cluster_config()
    bus = get_state_bus()

    return {
        "role": cfg.role,
        "node_id": cfg.node_id,
        "shard_count": cfg.shard_count,
        "redis_connected": bus.connected,
        "registered_shards": bus.list_shards(),
        "cluster_health": bus.get_cluster_health(),
    }


@router.post("/dispatch")
async def dispatch_task(req: DispatchRequest):
    """Route a task to the correct shard node via consistent hashing.

    The orchestrator hashes the task_id to determine which shard
    should process it, then forwards the request to that shard.
    """
    cfg = get_cluster_config()

    if cfg.role not in ("orchestrator", "standalone"):
        raise HTTPException(
            status_code=400,
            detail="Only the orchestrator can dispatch tasks",
        )

    task_id = req.task_id or str(uuid.uuid4())
    target_shard = assign_shard(task_id, cfg.shard_count)

    # Record assignment in the state bus
    bus = get_state_bus()
    bus.assign_task(task_id, target_shard, {"prompt": req.prompt[:200]})

    # Forward to the target shard
    shard_urls = _shard_urls()
    target_url = shard_urls.get(target_shard)

    if not target_url:
        raise HTTPException(
            status_code=503,
            detail=f"No URL known for shard {target_shard}",
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{target_url}/task/dispatch",
                json={
                    "task_id": task_id,
                    "prompt": req.prompt,
                    "metadata": req.metadata,
                },
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Shard {target_shard} rejected task: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to reach shard {target_shard} at {target_url}: {e}",
        )

    return {
        "task_id": task_id,
        "routed_to_shard": target_shard,
        "shard_url": target_url,
        "result": result,
    }


@router.post("/proof/challenge")
async def challenge_all_shards(req: ProofChallengeRequest):
    """Issue a storage proof challenge to every shard node.

    Returns attestation responses from all reachable shards.
    """
    cfg = get_cluster_config()
    nonce = req.nonce or uuid.uuid4().hex
    challenge_id = str(uuid.uuid4())

    shard_urls = _shard_urls()
    results = {}

    for shard_idx, url in sorted(shard_urls.items()):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{url}/proof/attest",
                    json={"challenge_id": challenge_id, "nonce": nonce},
                )
                resp.raise_for_status()
                results[f"shard-{shard_idx}"] = {
                    "status": "ok",
                    **resp.json(),
                }
        except Exception as e:
            results[f"shard-{shard_idx}"] = {
                "status": "error",
                "error": str(e),
            }

    passed = sum(1 for r in results.values() if r.get("status") == "ok")
    return {
        "challenge_id": challenge_id,
        "nonce": nonce,
        "shards_challenged": len(shard_urls),
        "shards_passed": passed,
        "results": results,
    }


@router.get("/health")
async def cluster_health():
    """Poll health of all shard nodes."""
    shard_urls = _shard_urls()
    health = {}

    for shard_idx, url in sorted(shard_urls.items()):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{url}/health")
                resp.raise_for_status()
                health[f"shard-{shard_idx}"] = {
                    "status": "healthy",
                    **resp.json(),
                }
        except Exception as e:
            health[f"shard-{shard_idx}"] = {
                "status": "unreachable",
                "error": str(e),
            }

    healthy = sum(1 for h in health.values() if h.get("status") == "healthy")
    return {
        "orchestrator": get_cluster_config().node_id,
        "shards_total": len(shard_urls),
        "shards_healthy": healthy,
        "nodes": health,
    }


@router.get("/routing/{task_id}")
async def preview_routing(task_id: str):
    """Preview which shard a task_id would be routed to."""
    cfg = get_cluster_config()
    target = assign_shard(task_id, cfg.shard_count)
    return {
        "task_id": task_id,
        "shard_count": cfg.shard_count,
        "assigned_shard": target,
    }
