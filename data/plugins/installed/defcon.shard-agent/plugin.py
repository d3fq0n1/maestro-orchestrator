"""
ShardNet Distributed Agent — Plugin wrapper.

This is the mod-manager-compatible wrapper around ShardAgent. When enabled
via the mod manager, it registers a ShardAgent instance with the orchestrator.
"""

from maestro.plugins.base import MaestroPlugin, PluginContext
from maestro.agents.shard import ShardAgent
from maestro.shard_registry import StorageNodeRegistry
from maestro.storage_proof import StorageProofEngine


class ShardAgentPlugin(MaestroPlugin):
    """Plugin that provides the ShardNet distributed inference agent."""

    def __init__(self):
        self._agent = None
        self._context = None

    def activate(self, context: PluginContext) -> bool:
        """Create and register a ShardAgent with the orchestrator."""
        self._context = context

        # Read config
        config = {}
        try:
            import json
            from pathlib import Path
            config_path = Path(context.data_dir).parent / "defcon.shard-agent" / "config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text())
        except Exception:
            pass

        model_id = config.get("model_id", "meta-llama/llama-3.3-70b-instruct")
        timeout = config.get("timeout_per_hop", 30.0)
        min_rep = config.get("min_reputation", 0.5)

        registry = context.get_registry() if callable(context.get_registry) else None
        proof_engine = None

        self._agent = ShardAgent(
            model_id=model_id,
            registry=registry or StorageNodeRegistry(),
            proof_engine=proof_engine,
            timeout_per_hop=timeout,
            min_reputation=min_rep,
        )

        if callable(context.register_agent):
            context.register_agent(self._agent)

        if context.log:
            context.log(f"ShardAgent activated: model={model_id}")

        return True

    def deactivate(self) -> bool:
        """Unregister the ShardAgent."""
        if self._agent and self._context and callable(self._context.unregister_agent):
            self._context.unregister_agent(self._agent)
        self._agent = None
        return True

    def health_check(self) -> dict:
        """Check if the agent is operational."""
        if not self._agent:
            return {"healthy": False, "message": "Agent not initialized", "metrics": {}}

        has_registry = self._agent.registry is not None
        node_count = len(self._agent.registry.list_nodes()) if has_registry else 0

        return {
            "healthy": has_registry and node_count > 0,
            "message": f"Registry: {'yes' if has_registry else 'no'}, Nodes: {node_count}",
            "metrics": {
                "model_id": self._agent.model_id,
                "node_count": node_count,
                "min_reputation": self._agent.min_reputation,
            },
        }

    def on_config_change(self, new_config: dict) -> bool:
        """Update agent config at runtime."""
        if self._agent and "model_id" in new_config:
            self._agent.model_id = new_config["model_id"]
            self._agent.model = new_config["model_id"]
        if self._agent and "timeout_per_hop" in new_config:
            self._agent.timeout_per_hop = new_config["timeout_per_hop"]
        if self._agent and "min_reputation" in new_config:
            self._agent.min_reputation = new_config["min_reputation"]
        return True
