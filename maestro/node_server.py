"""
Storage Node Server — Standalone FastAPI server for proof-of-storage nodes.

This is a SEPARATE PROCESS from the Maestro backend. Each storage node runs
its own instance of this server. The entire point is that storage nodes are
independent machines.

Usage:
    uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001

Endpoints:
    POST /infer       — Forward-pass inference on resident shards
    POST /challenge   — Respond to proof-of-storage challenges
    GET  /health      — Node health and status
    POST /heartbeat   — Acknowledge liveness
    GET  /shards      — List resident weight shards
"""

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Maestro Storage Node", version="0.6.0")

# Node identity — set via environment variables
NODE_ID = os.environ.get("MAESTRO_NODE_ID", "node-default")
NODE_STATUS = "available"
START_TIME = time.monotonic()

# In a real deployment, shards would be loaded into GPU/RAM here.
# For now, shard declarations are read from a config file.
SHARD_CONFIG_PATH = os.environ.get(
    "MAESTRO_SHARD_CONFIG", "data/node_shards.json"
)
_loaded_shards: list[dict] = []


def _load_shard_config():
    """Load shard declarations from config file."""
    global _loaded_shards
    if os.path.exists(SHARD_CONFIG_PATH):
        try:
            with open(SHARD_CONFIG_PATH) as f:
                _loaded_shards = json.load(f)
        except (json.JSONDecodeError, IOError):
            _loaded_shards = []


_load_shard_config()


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

    In production, this would:
      1. Deserialize input activations from base64
      2. Load the relevant weight shard layers
      3. Run the forward pass
      4. Serialize output activations to base64
      5. Return the result

    For now, this returns a mock response that simulates the pipeline.
    """
    # Simulate inference processing
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
        },
    }


@app.post("/challenge")
async def handle_challenge(challenge: ChallengeRequest):
    """
    Respond to a proof-of-storage challenge.

    Challenge types:
      - byte_range_hash: Hash a specific byte range of the shard file
      - latency_probe: Respond quickly to prove active residency
      - canary_inference: Run a known input through the shard
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
        # In production, we'd hash the actual bytes from the shard file.
        # For now, reproduce the expected hash using the same algorithm.
        computed = hashlib.sha256(
            f"{challenge.shard_id}:{challenge.byte_offset}:{challenge.byte_length}".encode()
        ).hexdigest()
        response["response_hash"] = computed

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
        "shards": _loaded_shards,
        "memory_used_mb": 0,  # would read from system in production
        "uptime_s": round(uptime, 1),
    }


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """Acknowledge liveness."""
    return {"ack": True, "node_id": NODE_ID}


@app.get("/shards")
async def list_shards():
    """List all resident weight shards."""
    return {"node_id": NODE_ID, "shards": _loaded_shards}
