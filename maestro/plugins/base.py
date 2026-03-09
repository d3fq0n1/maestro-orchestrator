"""
Plugin protocol and lifecycle management.

Every pluggable component in Maestro implements the MaestroPlugin protocol.
The mod manager discovers, validates, and manages plugin lifecycles.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PluginCategory(Enum):
    """Categories of plugins the mod manager recognizes."""
    AGENT = "agent"
    ANALYZER = "analyzer"
    AGGREGATOR = "aggregator"
    STORAGE_PROVIDER = "storage"
    OUTPUT_FORMAT = "output"
    PIPELINE_HOOK = "hook"
    PROOF_SYSTEM = "proof"
    EMBEDDING_PROVIDER = "embedding"


@dataclass
class PluginManifest:
    """
    Metadata describing a plugin. Every plugin directory must contain
    a manifest.json file with this structure.
    """
    plugin_id: str
    name: str
    version: str
    category: str
    description: str
    author: str
    entry_point: str
    class_name: str
    dependencies: list = field(default_factory=list)
    maestro_version_min: str = "0.5.0"
    maestro_version_max: Optional[str] = None
    config_schema: dict = field(default_factory=dict)
    permissions: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class PluginState(Enum):
    """Lifecycle states for a loaded plugin."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADED = "unloaded"


class MaestroPlugin(ABC):
    """
    Base class for all Maestro plugins.

    Every plugin must implement activate/deactivate for lifecycle management
    and health_check for monitoring. The mod manager calls these during
    state transitions.
    """

    @abstractmethod
    def activate(self, context: 'PluginContext') -> bool:
        """
        Called when the plugin transitions to ENABLED.
        Receives a PluginContext with references to Maestro internals.
        Return True on success, False on failure.
        """
        ...

    @abstractmethod
    def deactivate(self) -> bool:
        """Called when the plugin transitions to DISABLED or UNLOADED."""
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """
        Return plugin health status.
        Must return: {"healthy": bool, "message": str, "metrics": {}}
        """
        ...

    def on_config_change(self, new_config: dict) -> bool:
        """Called when plugin configuration is updated at runtime. Optional override."""
        return True


@dataclass
class PluginContext:
    """
    Injected into plugins on activation. Provides controlled access
    to Maestro internals without exposing everything.
    """
    maestro_version: str
    data_dir: str
    shared_data_dir: str
    get_registry: object = None
    get_r2_engine: object = None
    get_session_logger: object = None
    register_agent: object = None
    unregister_agent: object = None
    register_hook: object = None
    unregister_hook: object = None
    emit_event: object = None
    subscribe_event: object = None
    log: object = None
