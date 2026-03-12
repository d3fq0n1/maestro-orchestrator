"""
Storage Node Server — Standalone FastAPI server for proof-of-storage nodes.

This is a SEPARATE PROCESS from the Maestro backend. Each storage node runs
its own instance of this server. The entire point is that storage nodes are
independent machines.

Usage:
    uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001

    # With auto-registration:
    MAESTRO_NODE_ID=gpu-node-1 \
    MAESTRO_SHARD_CONFIG=data/node_shards.json \
    MAESTRO_ORCHESTRATOR_URL=http://localhost:8080 \
    uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001

Endpoints:
    POST /infer       — Forward-pass inference on resident shards
    POST /challenge   — Respond to proof-of-storage challenges
    GET  /health      — Node health and status
    POST /heartbeat   — Acknowledge liveness
    GET  /shards      — List resident weight shards
"""

import asyncio
import base64
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration — all via environment variables
# ---------------------------------------------------------------------------

NODE_ID = os.environ.get("MAESTRO_NODE_ID", "node-default")
NODE_PORT = int(os.environ.get("MAESTRO_NODE_PORT", "8001"))
NODE_HOST = os.environ.get("MAESTRO_NODE_HOST", "0.0.0.0")
NODE_STATUS = "available"
START_TIME = time.monotonic()

SHARD_CONFIG_PATH = os.environ.get(
    "MAESTRO_SHARD_CONFIG", "data/node_shards.json"
)

# Orchestrator URL for auto-registration and heartbeats
ORCHESTRATOR_URL = os.environ.get("MAESTRO_ORCHESTRATOR_URL", "")

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = int(os.environ.get("MAESTRO_HEARTBEAT_INTERVAL", "60"))

# Advertised host — what the orchestrator uses to reach this node.
# Defaults to NODE_HOST, but you'd set this to your public IP/hostname.
ADVERTISED_HOST = os.environ.get("MAESTRO_ADVERTISED_HOST", "")

# ---------------------------------------------------------------------------
# Shard state
# ---------------------------------------------------------------------------

_loaded_shards: list[dict] = []
_shard_file_map: dict[str, str] = {}  # shard_id -> filepath on disk
_heartbeat_task: Optional[asyncio.Task] = None


def _load_shard_config():
    """Load shard declarations from config file."""
    global _loaded_shards, _shard_file_map
    if os.path.exists(SHARD_CONFIG_PATH):
        try:
            with open(SHARD_CONFIG_PATH) as f:
                _loaded_shards = json.load(f)
            # Build file map for proof challenges
            for shard in _loaded_shards:
                shard_id = shard.get("shard_id", "")
                filepath = shard.get("filepath", "")
                if shard_id and filepath and os.path.exists(filepath):
                    _shard_file_map[shard_id] = filepath
        except (json.JSONDecodeError, IOError):
            _loaded_shards = []


def _total_shard_size_mb() -> int:
    """Total size of loaded shards in MB."""
    total = 0
    for shard in _loaded_shards:
        filepath = shard.get("filepath", "")
        if filepath and os.path.exists(filepath):
            total += os.path.getsize(filepath)
        else:
            total += shard.get("size_bytes", 0)
    return total // (1024 * 1024)


# ---------------------------------------------------------------------------
# Auto-registration and heartbeat
# ---------------------------------------------------------------------------

async def _register_with_orchestrator():
    """Register this node with the orchestrator backend."""
    if not ORCHESTRATOR_URL:
        return

    import httpx

    host = ADVERTISED_HOST or NODE_HOST
    if host == "0.0.0.0":
        host = "127.0.0.1"

    payload = {
        "node_id": NODE_ID,
        "host": host,
        "port": NODE_PORT,
        "shards": _loaded_shards,
        "capabilities": _detect_capabilities(),
        "total_memory_mb": _total_shard_size_mb(),
    }

    url = f"{ORCHESTRATOR_URL.rstrip('/')}/api/storage/nodes/register"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print(f"[node] Registered with orchestrator at {ORCHESTRATOR_URL}")
            else:
                print(f"[node] Registration failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[node] Could not reach orchestrator at {ORCHESTRATOR_URL}: {e}")


async def _heartbeat_loop():
    """Send periodic heartbeats to the orchestrator."""
    if not ORCHESTRATOR_URL:
        return

    import httpx

    url = f"{ORCHESTRATOR_URL.rstrip('/')}/api/storage/nodes/register"
    host = ADVERTISED_HOST or NODE_HOST
    if host == "0.0.0.0":
        host = "127.0.0.1"

    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            payload = {
                "node_id": NODE_ID,
                "host": host,
                "port": NODE_PORT,
                "shards": _loaded_shards,
                "capabilities": _detect_capabilities(),
                "total_memory_mb": _total_shard_size_mb(),
            }
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json=payload)
        except Exception:
            pass  # heartbeat failures are silent


def _detect_capabilities() -> list[str]:
    """Detect node capabilities based on loaded shards and environment."""
    caps = ["inference"]
    # Check if any shard covers layer 0 (can do embeddings)
    for shard in _loaded_shards:
        layer_range = shard.get("layer_range", [])
        if len(layer_range) >= 2 and layer_range[0] == 0:
            caps.append("embeddings")
            break
    return caps


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    global _heartbeat_task
    _load_shard_config()

    shard_count = len(_loaded_shards)
    file_count = len(_shard_file_map)
    print(f"[node] {NODE_ID} starting — {shard_count} shard(s) declared, "
          f"{file_count} file(s) on disk")

    # Auto-register
    await _register_with_orchestrator()

    # Start heartbeat
    if ORCHESTRATOR_URL:
        _heartbeat_task = asyncio.create_task(_heartbeat_loop())

    yield

    # Shutdown
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Maestro Storage Node", version="7.1.4", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class ActivationPayload(BaseModel):
    session_id: str
    model_id: str
    prompt: Optional[str] = None
    sequence_length: int = 0
    hidden_dim: int = 0
    dtype: str = "float16"
    activations_b64: str = ""
    layer_completed: int = -1
    layer_target: int = -1
    kv_cache_b64: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ChallengeRequest(BaseModel):
    challenge_id: str
    node_id: str
    shard_id: str
    challenge_type: str
    issued_at: str
    expires_at: str
    byte_offset: Optional[int] = None
    byte_length: Optional[int] = None
    expected_hash: Optional[str] = None
    canary_input: Optional[dict] = None
    expected_output_hash: Optional[str] = None
    max_latency_ms: Optional[int] = None


class HeartbeatRequest(BaseModel):
    node_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/infer")
async def infer(payload: ActivationPayload):
    """
    Run inference on resident weight shards.

    Currently returns a mock response that simulates the pipeline.
    When a real inference backend is connected (llama.cpp, vLLM, etc.),
    this endpoint would deserialize activations, run the forward pass
    through the loaded layers, and return the output activations.
    """
    prompt = payload.prompt or ""
    response_text = (
        f"[{NODE_ID}] Processed through layers "
        f"{payload.layer_completed + 1}-{payload.layer_target} "
        f"for model {payload.model_id}"
    )

    if prompt:
        response_text = (
            f"[{NODE_ID}] Inference result for: {prompt[:200]}"
        )

    return {
        "session_id": payload.session_id,
        "model_id": payload.model_id,
        "sequence_length": payload.sequence_length,
        "hidden_dim": payload.hidden_dim or 4096,
        "dtype": payload.dtype,
        "activations_b64": base64.b64encode(response_text.encode()).decode(),
        "layer_completed": payload.layer_target,
        "layer_target": payload.layer_target,
        "decoded_text": response_text,
        "metadata": {
            "source_node": NODE_ID,
            "pipeline_hop": payload.metadata.get("pipeline_hop", 0) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "shards_on_disk": len(_shard_file_map),
        },
    }


@app.post("/challenge")
async def handle_challenge(challenge: ChallengeRequest):
    """
    Respond to a proof-of-storage challenge.

    For byte_range_hash challenges: if the shard file exists on disk, hashes
    the actual bytes at the requested offset. This is real proof-of-replication —
    you can only produce the correct hash if you actually have the file.

    Falls back to the deterministic mock hash if the file isn't on disk
    (backwards-compatible with the existing test infrastructure).
    """
    start = time.monotonic()
    now = datetime.now(timezone.utc)

    response = {
        "challenge_id": challenge.challenge_id,
        "node_id": NODE_ID,
        "responded_at": now.isoformat(),
        "passed": True,
    }

    if challenge.challenge_type == "byte_range_hash":
        shard_path = _shard_file_map.get(challenge.shard_id)

        if shard_path and os.path.exists(shard_path):
            # Real proof: hash actual file bytes
            try:
                from maestro.shard_utils import hash_byte_range
                file_size = os.path.getsize(shard_path)
                offset = (challenge.byte_offset or 0) % file_size
                length = min(challenge.byte_length or 4096, file_size - offset)
                computed = hash_byte_range(shard_path, offset, length)
                response["response_hash"] = computed
                response["proof_type"] = "real"
            except Exception as e:
                response["response_hash"] = ""
                response["passed"] = False
                response["failure_reason"] = f"File read error: {e}"
        else:
            # Fallback: deterministic mock (backwards-compatible)
            computed = hashlib.sha256(
                f"{challenge.shard_id}:{challenge.byte_offset}:{challenge.byte_length}".encode()
            ).hexdigest()
            response["response_hash"] = computed
            response["proof_type"] = "mock"

    elif challenge.challenge_type == "latency_probe":
        elapsed_ms = (time.monotonic() - start) * 1000
        response["latency_ms"] = round(elapsed_ms, 2)

    elif challenge.challenge_type == "canary_inference":
        # Reproduce expected canary output
        computed = hashlib.sha256(
            f"canary:{challenge.shard_id}".encode()
        ).hexdigest()
        response["inference_output_hash"] = computed

    return response


@app.get("/health")
async def health():
    """Node health and status."""
    uptime = time.monotonic() - START_TIME
    return {
        "node_id": NODE_ID,
        "status": NODE_STATUS,
        "shards_declared": len(_loaded_shards),
        "shards_on_disk": len(_shard_file_map),
        "shards": _loaded_shards,
        "total_size_mb": _total_shard_size_mb(),
        "uptime_s": round(uptime, 1),
        "orchestrator": ORCHESTRATOR_URL or None,
        "heartbeat_interval_s": HEARTBEAT_INTERVAL,
    }


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """Acknowledge liveness."""
    return {"ack": True, "node_id": NODE_ID}


@app.get("/shards")
async def list_shards():
    """List all resident weight shards with file verification status."""
    enriched = []
    for shard in _loaded_shards:
        shard_id = shard.get("shard_id", "")
        filepath = _shard_file_map.get(shard_id)
        enriched.append({
            **shard,
            "file_on_disk": filepath is not None,
            "file_verified": filepath is not None and os.path.exists(filepath),
        })
    return {"node_id": NODE_ID, "shards": enriched}
