# Mod Manager — Modular Plugin Architecture

**Version:** v7.2.5
**Last Updated:** 2026-03-17
**Maintainer:** defcon

The Mod Manager is Maestro's plugin system. It discovers, validates, loads, and manages the lifecycle of modular extensions — agents, analyzers, storage providers, pipeline hooks, and more — without modifying the core orchestration code.

---

## Overview

The plugin architecture has four layers:

```
1. Plugin Protocol    — MaestroPlugin ABC + PluginManifest + PluginContext
2. Mod Manager        — Lifecycle management, hook system, event bus
3. Weight Snapshots   — Save/restore/diff system configurations
4. REST API + CLI     — Runtime management without restarts
```

All four layers are additive. The orchestration pipeline is unchanged when `mod_manager=None`.

---

## Plugin Protocol (`maestro/plugins/base.py`)

### MaestroPlugin

Every plugin extends this abstract base class:

```python
class MaestroPlugin(ABC):
    @abstractmethod
    def activate(self, context: PluginContext) -> bool:
        """Called when transitioning to ENABLED. Return True on success."""
        ...

    @abstractmethod
    def deactivate(self) -> bool:
        """Called when transitioning to DISABLED or UNLOADED."""
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """Return {"healthy": bool, "message": str, "metrics": {}}"""
        ...

    def on_config_change(self, new_config: dict) -> bool:
        """Called when config is updated at runtime. Optional."""
        return True
```

### PluginManifest

Every plugin directory contains a `manifest.json`:

```json
{
    "plugin_id": "defcon.shard-agent",
    "name": "Shard Agent Plugin",
    "version": "0.1.0",
    "category": "agent",
    "description": "Distributed inference agent via proof-of-storage network",
    "author": "defcon",
    "entry_point": "plugin",
    "class_name": "ShardAgentPlugin",
    "dependencies": [],
    "maestro_version_min": "0.6.0",
    "maestro_version_max": null,
    "config_schema": {},
    "permissions": ["network", "compute"],
    "tags": ["distributed", "inference"]
}
```

**Required fields:** `plugin_id`, `name`, `version`, `category`, `entry_point`, `class_name`

### PluginCategory

```python
class PluginCategory(Enum):
    AGENT = "agent"
    ANALYZER = "analyzer"
    AGGREGATOR = "aggregator"
    STORAGE_PROVIDER = "storage"
    OUTPUT_FORMAT = "output"
    PIPELINE_HOOK = "hook"
    PROOF_SYSTEM = "proof"
    EMBEDDING_PROVIDER = "embedding"
```

### PluginContext

Injected into plugins on activation. Provides controlled access to Maestro internals:

| Field | Type | Description |
|---|---|---|
| `maestro_version` | `str` | Current Maestro version |
| `data_dir` | `str` | Plugin-specific data directory |
| `shared_data_dir` | `str` | Shared data directory for inter-plugin data |
| `get_registry` | `callable` | Returns the StorageNodeRegistry (or None) |
| `get_r2_engine` | `callable` | Returns an R2Engine instance (or None) |
| `get_session_logger` | `callable` | Returns a SessionLogger instance (or None) |
| `register_agent` | `callable` | Register an agent with the council |
| `unregister_agent` | `callable` | Remove a plugin-registered agent |
| `register_hook` | `callable` | Register a pipeline hook (ownership tracked) |
| `unregister_hook` | `callable` | Remove a pipeline hook |
| `emit_event` | `callable` | Broadcast an event to subscribers |
| `subscribe_event` | `callable` | Subscribe to events from other plugins |
| `log` | `callable` | Plugin-scoped logger |

### PluginState

```
DISCOVERED → VALIDATED → LOADED → ENABLED ⇄ DISABLED → UNLOADED
                                     ↓
                                   ERROR
```

---

## Mod Manager (`maestro/plugins/manager.py`)

The ModManager is instantiated once at startup and persists for the lifetime of the process.

### Lifecycle Operations

| Method | Description |
|---|---|
| `discover()` | Scan `data/plugins/installed/` for `manifest.json` files |
| `validate(manifest)` | Check required fields, version compatibility, dependencies, permissions, entry point |
| `load(plugin_id)` | Import Python module, instantiate plugin class |
| `enable(plugin_id)` | Build PluginContext, call `plugin.activate(context)`, enable dependencies first |
| `disable(plugin_id)` | Call `plugin.deactivate()`, remove plugin hooks, transition to DISABLED |
| `unload(plugin_id)` | Remove from memory, clean up sys.modules |
| `reload(plugin_id)` | Hot-reload: unload, re-discover, load, re-enable if was enabled |

### Validation Checks

1. Required fields present
2. Category is recognized (`PluginCategory` enum)
3. Maestro version compatibility (min/max bounds)
4. Dependencies resolvable (other plugins loaded)
5. Entry point file exists on disk
6. Permissions are recognized (`network`, `filesystem`, `injection`, `compute`)

### Configuration

```python
manager = ModManager()

# Read config
config = manager.get_plugin_config("defcon.shard-agent")

# Update config (notifies plugin via on_config_change)
manager.update_plugin_config("defcon.shard-agent", {"timeout": 60})
```

Plugin configs are stored as `config.json` in the plugin directory.

---

## Pipeline Hooks

The orchestrator calls hooks at 8 points in the pipeline. Hooks run in registration order. A hook returning `None` skips modification. A hook that raises is caught and logged — never crashes the pipeline.

### Hook Points

| Hook | When | Context Keys |
|---|---|---|
| `pre_orchestration` | Before agents are called | `prompt` |
| `post_agent_response` | After each agent responds | `agent_name`, `response` |
| `pre_aggregation` | Before quorum aggregation | `responses`, `dissent` |
| `post_aggregation` | After aggregation | `consensus`, `agreement_ratio` |
| `pre_r2_scoring` | Before R2 scores the session | `session_data` |
| `post_r2_scoring` | After R2 scoring | `r2` |
| `pre_session_save` | Before session is persisted | `session_data` |
| `post_session_save` | After session is saved | `session_id` |

### Hook Registration

```python
# Direct registration
manager.register_hook("pre_orchestration", my_callback)

# Via PluginContext (ownership tracked for clean deactivation)
context.register_hook("pre_orchestration", my_callback)

# Async hooks are supported
async def async_hook(ctx):
    await some_async_work()
    return ctx

manager.register_hook("post_aggregation", async_hook)
```

When a plugin is disabled, all hooks it registered through its PluginContext are automatically removed.

### Hook Execution

```python
# Called by the orchestrator at each hook point
context = await manager.run_hooks("pre_orchestration", {"prompt": user_prompt})
```

Hooks receive a context dict, can modify it, and return the modified dict. The modified context flows to the next hook and then back to the orchestrator.

---

## Event Bus

Plugins can communicate with each other through the event bus without direct coupling.

```python
# Publisher
context.emit_event("shard_verified", {"node_id": "gpu-1", "passed": True})

# Subscriber
def on_shard_verified(data):
    print(f"Node {data['node_id']} verification: {data['passed']}")

context.subscribe_event("shard_verified", on_shard_verified)
```

Event handlers that raise are caught and logged — never crash other subscribers.

---

## Weight State Snapshots

Snapshots capture the entire system configuration at a point in time. Use them to save known-good states, experiment with changes, and roll back if something breaks.

### What a Snapshot Captures

- Which plugins are enabled/disabled
- Plugin configurations
- Active agent list
- Runtime config overlay (`data/runtime_config.json`)
- Storage node registry state (when available)

### Operations

```python
manager = ModManager()

# Save current state
snap = manager.save_snapshot("pre-experiment", description="Before testing new plugin")

# List saved snapshots
snapshots = manager.list_snapshots()

# Compare two snapshots
diff = manager.diff_snapshots("snap-abc123", "snap-def456")
# {
#     "plugins_added": ["defcon.new-analyzer"],
#     "plugins_removed": [],
#     "config_changes": {"defcon.shard-agent": {"from": {...}, "to": {...}}},
#     "agent_changes": {"from": ["GPT-4o", "Claude"], "to": ["GPT-4o", "Claude", "ShardNet"]},
# }

# Restore a previous state
manager.restore_snapshot("snap-abc123")

# Delete a snapshot
manager.delete_snapshot("snap-abc123")
```

Storage: `data/plugins/snapshots/`, one JSON file per snapshot.

---

## Plugin Directory Structure

```
data/plugins/
  ├── installed/
  │   └── defcon.shard-agent/
  │       ├── manifest.json          # Plugin metadata
  │       ├── plugin.py              # Entry point (class_name defined here)
  │       └── config.json            # Runtime configuration (optional)
  ├── disabled/                      # Reserved for disabled plugin storage
  └── snapshots/
      └── snap-abc123def456.json     # Weight state snapshot
```

---

## REST API

### Plugin Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/plugins` | List all plugins with state |
| POST | `/api/plugins/discover` | Scan for new plugins |
| POST | `/api/plugins/{plugin_id}/enable` | Load and enable a plugin |
| POST | `/api/plugins/{plugin_id}/disable` | Disable a plugin |
| POST | `/api/plugins/{plugin_id}/reload` | Hot-reload a plugin |
| GET | `/api/plugins/{plugin_id}` | Detailed plugin info with health |
| PUT | `/api/plugins/{plugin_id}/config` | Update plugin configuration |
| GET | `/api/plugins/health` | Health check all enabled plugins |

### Snapshot Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/snapshots` | List all snapshots |
| POST | `/api/snapshots` | Create a new snapshot |
| POST | `/api/snapshots/{id}/restore` | Restore a snapshot |
| GET | `/api/snapshots/{id}` | Load full snapshot data |
| DELETE | `/api/snapshots/{id}` | Delete a snapshot |
| GET | `/api/snapshots/diff/{a}/{b}` | Compare two snapshots |

---

## CLI Commands

| Command | Description |
|---|---|
| `/plugins` | List all plugins with state and health |
| `/snapshot` | Save or manage weight state snapshots |

---

## Writing a Plugin

### 1. Create the plugin directory

```
data/plugins/installed/myorg.my-plugin/
  ├── manifest.json
  └── plugin.py
```

### 2. Write the manifest

```json
{
    "plugin_id": "myorg.my-plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "category": "hook",
    "description": "Example pipeline hook plugin",
    "author": "myorg",
    "entry_point": "plugin",
    "class_name": "MyPlugin",
    "maestro_version_min": "0.6.0",
    "permissions": []
}
```

### 3. Implement the plugin class

```python
from maestro.plugins.base import MaestroPlugin, PluginContext

class MyPlugin(MaestroPlugin):
    def activate(self, context: PluginContext) -> bool:
        self.context = context

        # Register a hook
        context.register_hook("pre_orchestration", self._on_pre_orchestration)

        # Subscribe to events
        context.subscribe_event("session_complete", self._on_session)

        context.log("Plugin activated")
        return True

    def deactivate(self) -> bool:
        return True

    def health_check(self) -> dict:
        return {"healthy": True, "message": "OK", "metrics": {}}

    def _on_pre_orchestration(self, ctx):
        ctx["prompt"] = ctx["prompt"] + " [enhanced by MyPlugin]"
        return ctx

    def _on_session(self, data):
        self.context.log(f"Session completed: {data.get('session_id')}")
```

### 4. Enable the plugin

```bash
# Via CLI
maestro> /plugins

# Via API
curl -X POST http://localhost:8000/api/plugins/myorg.my-plugin/enable
```

---

## Design Principles

1. **Additive only** — The pipeline is identical without the mod manager. All hook calls are guarded by `if mod_manager:`.
2. **Fail-open** — A plugin hook that raises is caught and logged. The pipeline continues. A plugin that fails to activate doesn't block other plugins.
3. **Ownership tracking** — Hooks registered through PluginContext are tracked by plugin ID. When a plugin is disabled, all its hooks are automatically removed.
4. **No implicit state** — All plugin data is human-readable JSON on disk. No databases, no hidden state.
5. **Controlled access** — Plugins receive a PluginContext with specific callbacks, not a reference to the entire system. Access is scoped.

---

## See Also

- [`storage-network.md`](./storage-network.md) — Storage network (ShardAgent plugin is the reference example)
- [`architecture.md`](./architecture.md) — System architecture overview
- [`self-improvement-pipeline.md`](./self-improvement-pipeline.md) — Self-improvement pipeline (now injectable categories include `storage` and `module`)
