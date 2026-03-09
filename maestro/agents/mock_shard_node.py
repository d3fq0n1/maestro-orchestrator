"""
Mock Storage Node — In-process mock for testing distributed inference.

Pretends to be a storage node, accepting activation payloads and returning
fake next-stage activations. Lets you test the full pipeline without actual
GPU nodes.
"""

import base64
from datetime import datetime, timezone


class MockShardNode:
    """In-process mock of a storage node for testing."""

    def __init__(self, node_id: str, model_id: str, layer_range: tuple):
        self.node_id = node_id
        self.model_id = model_id
        self.layer_range = layer_range

    async def handle_infer(self, payload: dict) -> dict:
        """Return a mock activation payload with the next layer range."""
        prompt = payload.get("prompt", "")
        # Generate a mock response based on the prompt
        mock_response = f"Mock inference from {self.node_id} (layers {self.layer_range[0]}-{self.layer_range[1]})"
        if prompt:
            mock_response = f"[{self.node_id}] Response to: {prompt[:100]}"

        return {
            "session_id": payload.get("session_id", ""),
            "model_id": payload.get("model_id", self.model_id),
            "sequence_length": payload.get("sequence_length", 0),
            "hidden_dim": payload.get("hidden_dim", 4096),
            "dtype": payload.get("dtype", "float16"),
            "activations_b64": base64.b64encode(mock_response.encode()).decode(),
            "layer_completed": self.layer_range[1],
            "layer_target": payload.get("layer_target", self.layer_range[1]),
            "decoded_text": mock_response,
            "metadata": {
                "source_node": self.node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    async def handle_challenge(self, challenge: dict) -> dict:
        """Always pass challenges (mock)."""
        return {
            "challenge_id": challenge.get("challenge_id", ""),
            "node_id": self.node_id,
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "response_hash": challenge.get("expected_hash", ""),
            "inference_output_hash": challenge.get("expected_output_hash", ""),
            "latency_ms": 5.0,
            "passed": True,
        }

    def health(self) -> dict:
        """Return mock health status."""
        return {
            "node_id": self.node_id,
            "status": "available",
            "shards": [{
                "model_id": self.model_id,
                "layer_range": list(self.layer_range),
            }],
            "memory_used_mb": 1024,
            "uptime_s": 3600,
        }
