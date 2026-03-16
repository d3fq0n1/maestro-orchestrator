"""
The Mod Manager — discovers, validates, loads, and manages the lifecycle
of all plugins.

Plugin directory structure:
  data/plugins/
    ├── installed/
    │   └── <plugin_id>/
    │       ├── manifest.json
    │       ├── <entry_point>.py
    │       └── config.json (optional)
    ├── disabled/
    └── snapshots/

Weight State Snapshots:
  A snapshot captures the entire system configuration:
    - Which plugins are enabled/disabled
    - Plugin configurations
    - Storage node registry state
    - Active agent list
    - Threshold values (quorum, similarity, drift)
    - Runtime config overlay
"""

import asyncio
import importlib
import importlib.util
import json
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.plugins.base import (
    MaestroPlugin,
    PluginManifest,
    PluginContext,
    PluginState,
    PluginCategory,
)


_MAESTRO_VERSION = "7.2.3"

# Valid hook points in the orchestration pipeline
HOOK_POINTS = (
    "pre_orchestration",
    "post_agent_response",
    "pre_aggregation",
    "post_aggregation",
    "pre_r2_scoring",
    "post_r2_scoring",
    "pre_session_save",
    "post_session_save",
)


@dataclass
class PluginRecord:
    """Internal tracking record for a loaded plugin."""
    manifest: PluginManifest
    state: PluginState
    instance: Optional[MaestroPlugin] = None
    module: object = None
    error: Optional[str] = None


@dataclass
class WeightStateSnapshot:
    """A frozen capture of the entire system configuration."""
    snapshot_id: str
    name: str
    created_at: str
    description: str = ""

    enabled_plugins: list = field(default_factory=list)
    disabled_plugins: list = field(default_factory=list)
    plugin_configs: dict = field(default_factory=dict)

    storage_nodes: list = field(default_factory=list)
    shard_assignments: dict = field(default_factory=dict)

    active_agents: list = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)
    runtime_config: dict = field(default_factory=dict)

    metadata: dict = field(default_factory=dict)


class ModManager:
    """
    Central plugin lifecycle manager.

    The ModManager is instantiated once at startup and persists for the
    lifetime of the orchestrator process.
    """

    def __init__(self, plugins_dir: str = None):
        self._plugins_dir = Path(plugins_dir) if plugins_dir else (
            Path(__file__).resolve().parent.parent.parent / "data" / "plugins"
        )
        self._installed_dir = self._plugins_dir / "installed"
        self._snapshots_dir = self._plugins_dir / "snapshots"
        self._installed_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Runtime state
        self._plugins: dict[str, PluginRecord] = {}
        self._event_subscribers: dict[str, list] = {}
        self._hooks: dict[str, list] = {hp: [] for hp in HOOK_POINTS}

        # External registrations (set by orchestrator at init)
        self._registered_agents: dict[str, object] = {}

        # Hook ownership tracking: {hook_point: [(plugin_id, callback)]}
        self._hook_owners: dict[str, list[tuple[str, callable]]] = {
            hp: [] for hp in HOOK_POINTS
        }

    # ------------------------------------------------------------------
    # Plugin context callbacks
    # ------------------------------------------------------------------

    def _get_registry_callback(self):
        """Return the StorageNodeRegistry if available."""
        try:
            from maestro.shard_registry import StorageNodeRegistry
            return StorageNodeRegistry()
        except Exception:
            return None

    def _get_r2_engine_callback(self):
        """Return an R2Engine instance."""
        try:
            from maestro.r2 import R2Engine
            return R2Engine()
        except Exception:
            return None

    def _get_session_logger_callback(self):
        """Return a SessionLogger instance."""
        try:
            from maestro.session import SessionLogger
            return SessionLogger()
        except Exception:
            return None

    def _register_agent(self, agent):
        """Register an agent provided by a plugin."""
        name = getattr(agent, 'name', str(agent))
        self._registered_agents[name] = agent

    def _unregister_agent(self, agent):
        """Remove a plugin-registered agent."""
        name = getattr(agent, 'name', str(agent))
        self._registered_agents.pop(name, None)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginManifest]:
        """
        Scan the installed plugins directory for manifest.json files.
        Returns list of PluginManifest objects. Does NOT load or validate.
        """
        manifests = []
        if not self._installed_dir.exists():
            return manifests

        for plugin_dir in self._installed_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text())
                manifest = PluginManifest(**{
                    k: v for k, v in data.items()
                    if k in PluginManifest.__dataclass_fields__
                })
                manifests.append(manifest)

                # Track as discovered if not already known
                if manifest.plugin_id not in self._plugins:
                    self._plugins[manifest.plugin_id] = PluginRecord(
                        manifest=manifest,
                        state=PluginState.DISCOVERED,
                    )
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                print(f"[ModManager] Invalid manifest in {plugin_dir.name}: {e}")
                continue

        return manifests

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, manifest: PluginManifest) -> tuple[bool, list[str]]:
        """
        Validate a plugin manifest:
          1. Required fields present
          2. Maestro version compatibility
          3. Dependencies resolvable
          4. Permissions are recognized
          5. Entry point file exists
          6. Class name importable (dry-run check)
        """
        errors = []

        # Required fields
        for field_name in ("plugin_id", "name", "version", "category", "entry_point", "class_name"):
            if not getattr(manifest, field_name, None):
                errors.append(f"Missing required field: {field_name}")

        # Category check
        valid_categories = {c.value for c in PluginCategory}
        if manifest.category not in valid_categories:
            errors.append(f"Unknown category: {manifest.category}. Valid: {valid_categories}")

        # Version compatibility
        if manifest.maestro_version_min:
            if _version_tuple(manifest.maestro_version_min) > _version_tuple(_MAESTRO_VERSION):
                errors.append(
                    f"Requires Maestro >= {manifest.maestro_version_min}, "
                    f"running {_MAESTRO_VERSION}"
                )

        if manifest.maestro_version_max:
            if _version_tuple(manifest.maestro_version_max) < _version_tuple(_MAESTRO_VERSION):
                errors.append(
                    f"Requires Maestro <= {manifest.maestro_version_max}, "
                    f"running {_MAESTRO_VERSION}"
                )

        # Dependencies
        for dep_id in manifest.dependencies:
            if dep_id not in self._plugins:
                errors.append(f"Unresolved dependency: {dep_id}")

        # Entry point file
        plugin_dir = self._installed_dir / manifest.plugin_id
        if plugin_dir.exists():
            entry_file = plugin_dir / f"{manifest.entry_point}.py"
            if not entry_file.exists():
                errors.append(f"Entry point not found: {entry_file}")

        # Recognized permissions
        known_permissions = {"network", "filesystem", "injection", "compute"}
        for perm in manifest.permissions:
            if perm not in known_permissions:
                errors.append(f"Unknown permission: {perm}")

        is_valid = len(errors) == 0
        if is_valid and manifest.plugin_id in self._plugins:
            self._plugins[manifest.plugin_id].state = PluginState.VALIDATED

        return is_valid, errors

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self, plugin_id: str) -> bool:
        """
        Import the plugin's Python module and instantiate its class.
        Transitions from DISCOVERED/VALIDATED to LOADED.
        """
        record = self._plugins.get(plugin_id)
        if not record:
            print(f"[ModManager] Plugin not found: {plugin_id}")
            return False

        if record.state == PluginState.ENABLED:
            return True  # already loaded and enabled

        plugin_dir = self._installed_dir / plugin_id
        entry_file = plugin_dir / f"{record.manifest.entry_point}.py"
        if not entry_file.exists():
            record.state = PluginState.ERROR
            record.error = f"Entry point not found: {entry_file}"
            return False

        try:
            module_name = f"maestro_plugin_{plugin_id.replace('.', '_').replace('-', '_')}"

            spec = importlib.util.spec_from_file_location(module_name, str(entry_file))
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            plugin_class = getattr(module, record.manifest.class_name, None)
            if plugin_class is None:
                record.state = PluginState.ERROR
                record.error = f"Class {record.manifest.class_name} not found in {entry_file}"
                return False

            instance = plugin_class()
            record.instance = instance
            record.module = module
            record.state = PluginState.LOADED
            record.error = None
            return True

        except Exception as e:
            record.state = PluginState.ERROR
            record.error = f"Load failed: {type(e).__name__}: {e}"
            print(f"[ModManager] {record.error}")
            return False

    def enable(self, plugin_id: str) -> bool:
        """
        Activate a loaded plugin:
          1. Construct PluginContext
          2. Call plugin.activate(context)
          3. Transition to ENABLED
        """
        record = self._plugins.get(plugin_id)
        if not record:
            return False

        if record.state == PluginState.ENABLED:
            return True

        if record.state not in (PluginState.LOADED, PluginState.DISABLED):
            # Try loading first
            if not self.load(plugin_id):
                return False

        # Build dependencies first
        for dep_id in record.manifest.dependencies:
            dep = self._plugins.get(dep_id)
            if dep and dep.state != PluginState.ENABLED:
                if not self.enable(dep_id):
                    record.state = PluginState.ERROR
                    record.error = f"Dependency {dep_id} failed to enable"
                    return False

        # Build context
        plugin_data_dir = self._plugins_dir / "data" / plugin_id
        plugin_data_dir.mkdir(parents=True, exist_ok=True)

        # Build register_hook wrapper that tracks ownership
        def _plugin_register_hook(hook_point, callback):
            self.register_hook(hook_point, callback)
            self._hook_owners.setdefault(hook_point, []).append((plugin_id, callback))

        context = PluginContext(
            maestro_version=_MAESTRO_VERSION,
            data_dir=str(plugin_data_dir),
            shared_data_dir=str(self._plugins_dir / "data" / "shared"),
            get_registry=self._get_registry_callback,
            get_r2_engine=self._get_r2_engine_callback,
            get_session_logger=self._get_session_logger_callback,
            register_agent=self._register_agent,
            unregister_agent=self._unregister_agent,
            register_hook=_plugin_register_hook,
            unregister_hook=self.unregister_hook,
            emit_event=self.emit_event,
            subscribe_event=self.subscribe_event,
            log=lambda msg: print(f"[Plugin:{plugin_id}] {msg}"),
        )

        try:
            success = record.instance.activate(context)
            if success:
                record.state = PluginState.ENABLED
                record.error = None
                return True
            else:
                record.state = PluginState.ERROR
                record.error = "activate() returned False"
                return False
        except Exception as e:
            record.state = PluginState.ERROR
            record.error = f"Activation failed: {type(e).__name__}: {e}"
            print(f"[ModManager] {record.error}")
            return False

    def disable(self, plugin_id: str) -> bool:
        """
        Deactivate an enabled plugin. Plugin remains in memory for quick re-enable.
        """
        record = self._plugins.get(plugin_id)
        if not record:
            return False

        if record.state != PluginState.ENABLED:
            return True  # already disabled

        try:
            if record.instance:
                record.instance.deactivate()
        except Exception as e:
            print(f"[ModManager] Deactivation error for {plugin_id}: {e}")

        # Remove any hooks this plugin registered
        self._remove_plugin_hooks(plugin_id)

        record.state = PluginState.DISABLED
        return True

    def unload(self, plugin_id: str) -> bool:
        """
        Remove a plugin from memory entirely.
        """
        record = self._plugins.get(plugin_id)
        if not record:
            return False

        if record.state == PluginState.ENABLED:
            self.disable(plugin_id)

        # Remove from sys.modules
        module_name = f"maestro_plugin_{plugin_id.replace('.', '_').replace('-', '_')}"
        sys.modules.pop(module_name, None)

        record.instance = None
        record.module = None
        record.state = PluginState.UNLOADED
        return True

    def reload(self, plugin_id: str) -> bool:
        """Hot-reload: unload then load+enable."""
        was_enabled = (
            self._plugins.get(plugin_id, PluginRecord(
                manifest=PluginManifest(
                    plugin_id="", name="", version="", category="",
                    description="", author="", entry_point="", class_name=""
                ),
                state=PluginState.UNLOADED,
            )).state == PluginState.ENABLED
        )
        self.unload(plugin_id)
        # Re-discover to pick up manifest changes
        self.discover()
        if not self.load(plugin_id):
            return False
        if was_enabled:
            return self.enable(plugin_id)
        return True

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_plugin_config(self, plugin_id: str) -> dict:
        """Read plugin's config.json."""
        config_path = self._installed_dir / plugin_id / "config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def update_plugin_config(self, plugin_id: str, updates: dict) -> bool:
        """Update config and notify plugin via on_config_change()."""
        config = self.get_plugin_config(plugin_id)
        config.update(updates)

        config_path = self._installed_dir / plugin_id / "config.json"
        config_path.write_text(json.dumps(config, indent=2))

        record = self._plugins.get(plugin_id)
        if record and record.instance and record.state == PluginState.ENABLED:
            try:
                record.instance.on_config_change(config)
            except Exception as e:
                print(f"[ModManager] Config change notification failed for {plugin_id}: {e}")

        return True

    # ------------------------------------------------------------------
    # Weight State Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(self, name: str, description: str = "") -> WeightStateSnapshot:
        """Capture current system state as a named snapshot."""
        enabled = []
        disabled = []
        configs = {}

        for pid, record in self._plugins.items():
            if record.state == PluginState.ENABLED:
                enabled.append(pid)
            elif record.state in (PluginState.DISABLED, PluginState.LOADED):
                disabled.append(pid)
            configs[pid] = self.get_plugin_config(pid)

        # Read runtime config if available
        runtime_config_path = (
            Path(__file__).resolve().parent.parent.parent / "data" / "runtime_config.json"
        )
        runtime_config = {}
        if runtime_config_path.exists():
            try:
                runtime_config = json.loads(runtime_config_path.read_text())
            except json.JSONDecodeError:
                pass

        snapshot = WeightStateSnapshot(
            snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
            name=name,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=description,
            enabled_plugins=enabled,
            disabled_plugins=disabled,
            plugin_configs=configs,
            active_agents=list(self._registered_agents.keys()),
            runtime_config=runtime_config,
        )

        filepath = self._snapshots_dir / f"{snapshot.snapshot_id}.json"
        filepath.write_text(json.dumps(asdict(snapshot), indent=2))
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restore system to a previously saved state:
          1. Disable all currently enabled plugins
          2. Load and enable plugins from snapshot
          3. Apply plugin configs from snapshot
        """
        filepath = self._snapshots_dir / f"{snapshot_id}.json"
        if not filepath.exists():
            print(f"[ModManager] Snapshot not found: {snapshot_id}")
            return False

        try:
            data = json.loads(filepath.read_text())
        except json.JSONDecodeError as e:
            print(f"[ModManager] Invalid snapshot file: {e}")
            return False

        # Disable all currently enabled plugins
        for pid, record in list(self._plugins.items()):
            if record.state == PluginState.ENABLED:
                self.disable(pid)

        # Re-discover to ensure we have all manifests
        self.discover()

        # Apply plugin configs
        for pid, config in data.get("plugin_configs", {}).items():
            if config:
                self.update_plugin_config(pid, config)

        # Enable plugins from snapshot
        for pid in data.get("enabled_plugins", []):
            if pid in self._plugins:
                self.load(pid)
                self.enable(pid)

        # Apply runtime config
        runtime_config = data.get("runtime_config", {})
        if runtime_config:
            config_path = (
                Path(__file__).resolve().parent.parent.parent / "data" / "runtime_config.json"
            )
            config_path.write_text(json.dumps(runtime_config, indent=2))

        return True

    def list_snapshots(self) -> list[dict]:
        """List all saved snapshots with metadata."""
        snapshots = []
        if not self._snapshots_dir.exists():
            return snapshots

        for filepath in sorted(self._snapshots_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(filepath.read_text())
                snapshots.append({
                    "snapshot_id": data["snapshot_id"],
                    "name": data["name"],
                    "created_at": data["created_at"],
                    "description": data.get("description", ""),
                    "enabled_plugins": len(data.get("enabled_plugins", [])),
                    "disabled_plugins": len(data.get("disabled_plugins", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return snapshots

    def load_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Load full snapshot data."""
        filepath = self._snapshots_dir / f"{snapshot_id}.json"
        if not filepath.exists():
            return None
        try:
            return json.loads(filepath.read_text())
        except json.JSONDecodeError:
            return None

    def diff_snapshots(self, snapshot_a_id: str, snapshot_b_id: str) -> dict:
        """Compare two snapshots and return the differences."""
        a = self.load_snapshot(snapshot_a_id)
        b = self.load_snapshot(snapshot_b_id)

        if not a or not b:
            return {"error": "One or both snapshots not found"}

        a_enabled = set(a.get("enabled_plugins", []))
        b_enabled = set(b.get("enabled_plugins", []))

        a_disabled = set(a.get("disabled_plugins", []))
        b_disabled = set(b.get("disabled_plugins", []))

        # Config diffs
        config_changes = {}
        all_plugins = set(list(a.get("plugin_configs", {}).keys()) +
                         list(b.get("plugin_configs", {}).keys()))
        for pid in all_plugins:
            a_conf = a.get("plugin_configs", {}).get(pid, {})
            b_conf = b.get("plugin_configs", {}).get(pid, {})
            if a_conf != b_conf:
                config_changes[pid] = {"from": a_conf, "to": b_conf}

        return {
            "snapshot_a": {"id": snapshot_a_id, "name": a.get("name", "")},
            "snapshot_b": {"id": snapshot_b_id, "name": b.get("name", "")},
            "plugins_added": sorted(b_enabled - a_enabled),
            "plugins_removed": sorted(a_enabled - b_enabled),
            "plugins_enabled": sorted(b_enabled - a_enabled - a_disabled),
            "plugins_disabled": sorted(b_disabled - a_disabled - a_enabled),
            "config_changes": config_changes,
            "agent_changes": {
                "from": a.get("active_agents", []),
                "to": b.get("active_agents", []),
            },
        }

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        filepath = self._snapshots_dir / f"{snapshot_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Event Bus
    # ------------------------------------------------------------------

    def emit_event(self, event_name: str, data: dict):
        """Broadcast an event to all subscribers."""
        for callback in self._event_subscribers.get(event_name, []):
            try:
                callback(data)
            except Exception as e:
                print(f"[ModManager] Event handler error for {event_name}: {e}")

    def subscribe_event(self, event_name: str, callback: callable):
        """Register a callback for an event type."""
        if event_name not in self._event_subscribers:
            self._event_subscribers[event_name] = []
        self._event_subscribers[event_name].append(callback)

    # ------------------------------------------------------------------
    # Pipeline Hooks
    # ------------------------------------------------------------------

    def register_hook(self, hook_point: str, callback: callable):
        """Register a callable at a specific pipeline hook point."""
        if hook_point not in self._hooks:
            raise ValueError(
                f"Unknown hook point: {hook_point}. "
                f"Valid: {list(self._hooks.keys())}"
            )
        self._hooks[hook_point].append(callback)

    def unregister_hook(self, hook_point: str, callback: callable):
        """Remove a hook callback."""
        if hook_point in self._hooks:
            try:
                self._hooks[hook_point].remove(callback)
            except ValueError:
                pass

    async def run_hooks(self, hook_point: str, context: dict) -> dict:
        """
        Execute all registered hooks at a pipeline point.
        Hooks can modify the context dict. Hooks run in registration order.
        A hook returning None skips modification.
        """
        for hook in self._hooks.get(hook_point, []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    result = await hook(context)
                else:
                    result = hook(context)
                if result is not None:
                    context = result
            except Exception as e:
                print(f"[ModManager] Hook error at {hook_point}: {e}")
        return context

    def _remove_plugin_hooks(self, plugin_id: str):
        """Remove all hooks registered by a specific plugin."""
        for hook_point in HOOK_POINTS:
            owned = [
                (pid, cb) for pid, cb in self._hook_owners.get(hook_point, [])
                if pid == plugin_id
            ]
            for pid, cb in owned:
                try:
                    self._hooks[hook_point].remove(cb)
                except ValueError:
                    pass
            self._hook_owners[hook_point] = [
                (pid, cb) for pid, cb in self._hook_owners.get(hook_point, [])
                if pid != plugin_id
            ]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[dict]:
        """List all known plugins with their current state."""
        result = []
        for pid, record in self._plugins.items():
            result.append({
                "plugin_id": pid,
                "name": record.manifest.name,
                "version": record.manifest.version,
                "category": record.manifest.category,
                "state": record.state.value,
                "error": record.error,
            })
        return result

    def get_plugin_info(self, plugin_id: str) -> Optional[dict]:
        """Detailed info about a specific plugin."""
        record = self._plugins.get(plugin_id)
        if not record:
            return None

        info = asdict(record.manifest)
        info["state"] = record.state.value
        info["error"] = record.error
        info["config"] = self.get_plugin_config(plugin_id)

        if record.instance and record.state == PluginState.ENABLED:
            try:
                info["health"] = record.instance.health_check()
            except Exception as e:
                info["health"] = {"healthy": False, "message": str(e), "metrics": {}}

        return info

    def health_check_all(self) -> dict:
        """Run health checks on all enabled plugins."""
        results = {}
        for pid, record in self._plugins.items():
            if record.state == PluginState.ENABLED and record.instance:
                try:
                    results[pid] = record.instance.health_check()
                except Exception as e:
                    results[pid] = {"healthy": False, "message": str(e), "metrics": {}}
        return results


def _version_tuple(version_str: str) -> tuple:
    """Parse a semver string into a comparable tuple."""
    try:
        parts = version_str.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)
