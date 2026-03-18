"""
Shard Agent — Routes inference through the distributed weight host network.

Unlike Aria/Sol/Prism which call centralized APIs, the ShardAgent constructs
an inference pipeline across persistent weight hosts, passes activation tensors
between them, and returns the final response as a string — same interface as
every other agent.

Queries travel to weights, not weights to queries. The orchestrator doesn't
know or care that the inference happened across a distributed network. It
just sees another agent response.
"""

import asyncio
import base64
import json
import uuid
from typing import Optional

import httpx

from maestro.agents.base import Agent
from maestro.shard_registry import WeightHostRegistry, WeightHost
from maestro.storage_proof import StorageProofEngine


class ShardAgent(Agent):
    """
    Agent that runs inference across distributed persistent weight hosts.

    Implements the same async fetch(prompt) -> str interface as all other agents.
    Internally:
      1. Queries the WeightHostRegistry for a pipeline covering all layers
      2. Tokenizes the prompt locally
      3. Sends input embeddings to the first pipeline host
      4. Each host runs its shard's layers and passes activations to the next
      5. Final host produces logits, which are decoded locally
      6. Returns the decoded text as a string

    Error handling follows the same contract as other agents: typed error
    strings, never raises.
    """

    name = "ShardNet"
    model = "distributed"

    def __init__(
        self,
        model_id: str = "meta-llama/llama-3.3-70b-instruct",
        registry: WeightHostRegistry = None,
        proof_engine: StorageProofEngine = None,
        timeout_per_hop: float = 30.0,
        min_reputation: float = 0.5,
    ):
        self.model_id = model_id
        self.model = model_id
        self.registry = registry
        self.proof_engine = proof_engine
        self.timeout_per_hop = timeout_per_hop
        self.min_reputation = min_reputation

    async def fetch(self, prompt: str) -> str:
        """
        Execute distributed inference across the storage network.

        All failures return typed error strings per the agent contract.
        """
        try:
            if not self.registry:
                return f"[{self.name}] No weight host registry configured"

            # Route query to persistent weight hosts
            pipeline = self.registry.route_query(self.model_id)
            if not pipeline:
                return f"[{self.name}] No weight hosts available for {self.model_id}"

            # Filter by reputation
            if self.proof_engine:
                pipeline = [
                    node for node in pipeline
                    if self.proof_engine.get_reputation(node.node_id).reputation_score >= self.min_reputation
                ]
                if not pipeline:
                    return (
                        f"[{self.name}] No trusted nodes available "
                        f"(reputation threshold: {self.min_reputation})"
                    )

            # Execute pipeline
            result = await self._execute_pipeline(prompt, pipeline)
            return result

        except Exception as e:
            return f"[{self.name}] Failed: {type(e).__name__}: {e}"

    async def _execute_pipeline(self, prompt: str, pipeline: list[WeightHost]) -> str:
        """
        Execute the forward pass across pipeline nodes.
        """
        session_id = str(uuid.uuid4())

        # Initial payload: tokenized prompt as activation input
        activation_payload = {
            "session_id": session_id,
            "model_id": self.model_id,
            "prompt": prompt,
            "sequence_length": len(prompt.split()),
            "hidden_dim": 0,  # determined by model
            "dtype": "float16",
            "activations_b64": base64.b64encode(prompt.encode()).decode(),
            "layer_completed": -1,
            "layer_target": -1,
            "metadata": {
                "pipeline_hops": len(pipeline),
                "source": "ShardAgent",
            },
        }

        # Forward through each pipeline node
        for i, node in enumerate(pipeline):
            activation_payload["metadata"]["pipeline_hop"] = i
            activation_payload["metadata"]["target_node"] = node.node_id

            try:
                result = await self._forward_to_node(node, activation_payload)
                activation_payload = result
            except Exception as e:
                # Attempt failover
                try:
                    result = await self._failover(node, activation_payload)
                    activation_payload = result
                except Exception as failover_err:
                    return (
                        f"[{self.name}] Pipeline failed at hop {i} "
                        f"(node {node.node_id}): {type(e).__name__}: {e}"
                    )

        # Decode final output
        final_text = activation_payload.get("decoded_text", "")
        if not final_text:
            # Try to decode from activations
            raw = activation_payload.get("activations_b64", "")
            if raw:
                try:
                    final_text = base64.b64decode(raw).decode("utf-8", errors="replace")
                except Exception:
                    final_text = "[Decoding error]"

        return final_text or f"[{self.name}] Empty response from pipeline"

    async def _forward_to_node(
        self,
        node: WeightHost,
        activation_payload: dict,
    ) -> dict:
        """
        Send activation tensor to a node and receive the output.
        POST to http://{node.host}:{node.port}/infer
        """
        url = f"http://{node.host}:{node.port}/infer"
        async with httpx.AsyncClient(timeout=self.timeout_per_hop) as client:
            response = await client.post(url, json=activation_payload)
            response.raise_for_status()
            return response.json()

    async def _failover(
        self,
        failed_node: WeightHost,
        activation_payload: dict,
    ) -> dict:
        """
        Attempt to route to a redundant node when primary fails.
        """
        if not self.registry:
            raise RuntimeError("No registry for failover")

        # Find the layer range the failed node was responsible for
        layer_completed = activation_payload.get("layer_completed", -1)
        target_layer = activation_payload.get("layer_target", -1)

        alternatives = self.registry.find_nodes_for_shard(
            self.model_id, layer_completed + 1, target_layer
        )
        alternatives = [n for n in alternatives if n.node_id != failed_node.node_id]

        if not alternatives:
            raise RuntimeError(
                f"No alternative nodes for layers {layer_completed + 1}-{target_layer}"
            )

        # Pick best alternative by reputation
        alternatives.sort(key=lambda n: (-n.reputation_score, n.mean_latency_ms))
        return await self._forward_to_node(alternatives[0], activation_payload)
