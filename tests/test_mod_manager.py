"""
Tests for the Mod Manager — plugin lifecycle, discovery, validation,
snapshots, hooks, and event bus.
"""

import json
import tempfile
from pathlib import Path

import pytest

from maestro.plugins.base import (
    MaestroPlugin,
    PluginManifest,
    PluginContext,
    PluginState,
    PluginCategory,
)
from maestro.plugins.manager import ModManager, WeightStateSnapshot, HOOK_POINTS


# ---------------------------------------------------------------------------
# Test plugin implementation
# ---------------------------------------------------------------------------

class _TestPlugin(MaestroPlugin):
    """Minimal plugin for testing."""
    activated = False
    deactivated = False

    def activate(self, context):
        _TestPlugin.activated = True
        return True

    def deactivate(self):
        _TestPlugin.deactivated = True
        return True

    def health_check(self):
        return {"healthy": True, "message": "ok", "metrics": {}}


def _make_plugin_dir(base: Path, plugin_id: str = "test.plugin"):
    """Create a plugin directory with manifest and entry point."""
    plugin_dir = base / "installed" / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "plugin_id": plugin_id,
        "name": "Test Plugin",
        "version": "1.0.0",
        "category": "agent",
        "description": "A test plugin",
        "author": "test",
        "entry_point": "plugin",
        "class_name": "TestPlugin",
        "maestro_version_min": "0.5.0",
        "permissions": ["network"],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))

    # Write the plugin code
    code = '''
from maestro.plugins.base import MaestroPlugin

class TestPlugin(MaestroPlugin):
    activated = False
    deactivated = False

    def activate(self, context):
        TestPlugin.activated = True
        return True

    def deactivate(self):
        TestPlugin.deactivated = True
        return True

    def health_check(self):
        return {"healthy": True, "message": "ok", "metrics": {}}
'''
    (plugin_dir / "plugin.py").write_text(code)
    return plugin_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModManagerDiscovery:
    def test_discover_finds_plugins(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.alpha")
        _make_plugin_dir(tmp_path, "test.beta")
        mgr = ModManager(plugins_dir=str(tmp_path))
        manifests = mgr.discover()
        ids = {m.plugin_id for m in manifests}
        assert "test.alpha" in ids
        assert "test.beta" in ids

    def test_discover_empty_dir(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        assert mgr.discover() == []

    def test_discover_skips_invalid_manifests(self, tmp_path):
        bad_dir = tmp_path / "installed" / "bad.plugin"
        bad_dir.mkdir(parents=True)
        (bad_dir / "manifest.json").write_text("not json")
        mgr = ModManager(plugins_dir=str(tmp_path))
        assert mgr.discover() == []


class TestModManagerValidation:
    def test_validate_good_manifest(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.valid")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        manifest = mgr._plugins["test.valid"].manifest
        is_valid, errors = mgr.validate(manifest)
        assert is_valid
        assert errors == []

    def test_validate_missing_entry_point(self, tmp_path):
        plugin_dir = tmp_path / "installed" / "test.noentry"
        plugin_dir.mkdir(parents=True)
        manifest_data = {
            "plugin_id": "test.noentry",
            "name": "No Entry",
            "version": "1.0.0",
            "category": "agent",
            "description": "Missing entry",
            "author": "test",
            "entry_point": "nonexistent",
            "class_name": "Foo",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest_data))
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        manifest = mgr._plugins["test.noentry"].manifest
        is_valid, errors = mgr.validate(manifest)
        assert not is_valid
        assert any("Entry point" in e for e in errors)

    def test_validate_bad_category(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.badcat")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr._plugins["test.badcat"].manifest.category = "invalid_cat"
        is_valid, errors = mgr.validate(mgr._plugins["test.badcat"].manifest)
        assert not is_valid
        assert any("Unknown category" in e for e in errors)


class TestModManagerLifecycle:
    def test_load_plugin(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.load")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        assert mgr.load("test.load")
        assert mgr._plugins["test.load"].state == PluginState.LOADED

    def test_enable_plugin(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.enable")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.enable")
        assert mgr.enable("test.enable")
        assert mgr._plugins["test.enable"].state == PluginState.ENABLED

    def test_disable_plugin(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.disable")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.disable")
        mgr.enable("test.disable")
        assert mgr.disable("test.disable")
        assert mgr._plugins["test.disable"].state == PluginState.DISABLED

    def test_unload_plugin(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.unload")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.unload")
        mgr.enable("test.unload")
        assert mgr.unload("test.unload")
        assert mgr._plugins["test.unload"].state == PluginState.UNLOADED
        assert mgr._plugins["test.unload"].instance is None

    def test_reload_plugin(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.reload")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.reload")
        mgr.enable("test.reload")
        assert mgr.reload("test.reload")
        assert mgr._plugins["test.reload"].state == PluginState.ENABLED

    def test_full_lifecycle(self, tmp_path):
        """discover -> validate -> load -> enable -> disable -> unload"""
        _make_plugin_dir(tmp_path, "test.lifecycle")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        assert mgr._plugins["test.lifecycle"].state == PluginState.DISCOVERED

        ok, _ = mgr.validate(mgr._plugins["test.lifecycle"].manifest)
        assert ok

        assert mgr.load("test.lifecycle")
        assert mgr._plugins["test.lifecycle"].state == PluginState.LOADED

        assert mgr.enable("test.lifecycle")
        assert mgr._plugins["test.lifecycle"].state == PluginState.ENABLED

        assert mgr.disable("test.lifecycle")
        assert mgr._plugins["test.lifecycle"].state == PluginState.DISABLED

        assert mgr.unload("test.lifecycle")
        assert mgr._plugins["test.lifecycle"].state == PluginState.UNLOADED


class TestModManagerConfig:
    def test_get_set_config(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.config")
        mgr = ModManager(plugins_dir=str(tmp_path))
        assert mgr.get_plugin_config("test.config") == {}
        mgr.update_plugin_config("test.config", {"key": "value"})
        assert mgr.get_plugin_config("test.config") == {"key": "value"}


class TestModManagerHooks:
    def test_register_and_run_hooks(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        called = []

        def hook(ctx):
            called.append(ctx)
            return ctx

        mgr.register_hook("pre_orchestration", hook)

        import asyncio
        result = asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "test"}))
        assert len(called) == 1
        assert called[0]["prompt"] == "test"

    def test_hook_modifies_context(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))

        def uppercase_hook(ctx):
            ctx["prompt"] = ctx["prompt"].upper()
            return ctx

        mgr.register_hook("pre_orchestration", uppercase_hook)

        import asyncio
        result = asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "hello"}))
        assert result["prompt"] == "HELLO"

    def test_async_hook(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))

        async def async_hook(ctx):
            ctx["async"] = True
            return ctx

        mgr.register_hook("post_aggregation", async_hook)

        import asyncio
        result = asyncio.run(mgr.run_hooks("post_aggregation", {}))
        assert result["async"] is True

    def test_invalid_hook_point_raises(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Unknown hook point"):
            mgr.register_hook("nonexistent_hook", lambda x: x)

    def test_unregister_hook(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        called = []
        hook = lambda ctx: called.append(1)
        mgr.register_hook("pre_orchestration", hook)
        mgr.unregister_hook("pre_orchestration", hook)

        import asyncio
        asyncio.run(mgr.run_hooks("pre_orchestration", {}))
        assert len(called) == 0

    def test_all_hook_points_exist(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        for hp in HOOK_POINTS:
            assert hp in mgr._hooks


class TestModManagerEvents:
    def test_emit_and_subscribe(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        received = []
        mgr.subscribe_event("test_event", lambda d: received.append(d))
        mgr.emit_event("test_event", {"key": "value"})
        assert len(received) == 1
        assert received[0]["key"] == "value"


class TestWeightStateSnapshots:
    def test_save_and_list(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap = mgr.save_snapshot("test_snap", "A test snapshot")
        assert snap.name == "test_snap"
        assert snap.snapshot_id.startswith("snap-")

        snapshots = mgr.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["name"] == "test_snap"

    def test_save_and_restore(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.snaprestore")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.snaprestore")
        mgr.enable("test.snaprestore")

        snap = mgr.save_snapshot("before_change")
        assert "test.snaprestore" in snap.enabled_plugins

        # Disable the plugin
        mgr.disable("test.snaprestore")

        # Restore
        assert mgr.restore_snapshot(snap.snapshot_id)
        assert mgr._plugins["test.snaprestore"].state == PluginState.ENABLED

    def test_diff_snapshots(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap_a = mgr.save_snapshot("snap_a")
        snap_b = mgr.save_snapshot("snap_b")
        diff = mgr.diff_snapshots(snap_a.snapshot_id, snap_b.snapshot_id)
        assert "snapshot_a" in diff
        assert "snapshot_b" in diff

    def test_delete_snapshot(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap = mgr.save_snapshot("to_delete")
        assert mgr.delete_snapshot(snap.snapshot_id)
        assert mgr.list_snapshots() == []

    def test_load_snapshot_data(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap = mgr.save_snapshot("detailed", "full details")
        data = mgr.load_snapshot(snap.snapshot_id)
        assert data is not None
        assert data["name"] == "detailed"
        assert data["description"] == "full details"


class TestModManagerIntrospection:
    def test_list_plugins(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.list")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        plugins = mgr.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["plugin_id"] == "test.list"
        assert plugins[0]["state"] == "discovered"

    def test_get_plugin_info(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.info")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        info = mgr.get_plugin_info("test.info")
        assert info is not None
        assert info["plugin_id"] == "test.info"

    def test_health_check_all(self, tmp_path):
        _make_plugin_dir(tmp_path, "test.health")
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.health")
        mgr.enable("test.health")
        health = mgr.health_check_all()
        assert "test.health" in health
        assert health["test.health"]["healthy"] is True
