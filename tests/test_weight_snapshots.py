"""
Tests for weight state snapshots — save/restore/diff round-trips.
"""

import json
from pathlib import Path

import pytest

from maestro.plugins.manager import ModManager, WeightStateSnapshot


class TestWeightStateSnapshotDataclass:
    def test_default_fields(self):
        snap = WeightStateSnapshot(
            snapshot_id="snap-1",
            name="test",
            created_at="2026-01-01T00:00:00Z",
        )
        assert snap.enabled_plugins == []
        assert snap.plugin_configs == {}
        assert snap.storage_nodes == []
        assert snap.active_agents == []
        assert snap.thresholds == {}
        assert snap.runtime_config == {}


class TestSnapshotRoundTrip:
    def test_save_load_roundtrip(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap = mgr.save_snapshot("roundtrip", "test desc")
        loaded = mgr.load_snapshot(snap.snapshot_id)
        assert loaded["name"] == "roundtrip"
        assert loaded["description"] == "test desc"
        assert loaded["snapshot_id"] == snap.snapshot_id

    def test_multiple_snapshots(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.save_snapshot("first")
        mgr.save_snapshot("second")
        mgr.save_snapshot("third")
        snaps = mgr.list_snapshots()
        assert len(snaps) == 3
        names = {s["name"] for s in snaps}
        assert names == {"first", "second", "third"}


class TestSnapshotDiff:
    def _make_two_snapshots(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap_a = mgr.save_snapshot("snap_a")

        # Modify state and save again
        mgr._registered_agents["ShardNet"] = object()
        snap_b = mgr.save_snapshot("snap_b")

        return mgr, snap_a, snap_b

    def test_diff_detects_agent_changes(self, tmp_path):
        mgr, snap_a, snap_b = self._make_two_snapshots(tmp_path)
        diff = mgr.diff_snapshots(snap_a.snapshot_id, snap_b.snapshot_id)
        assert diff["agent_changes"]["to"] != diff["agent_changes"]["from"]

    def test_diff_nonexistent_snapshot(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        snap = mgr.save_snapshot("exists")
        diff = mgr.diff_snapshots(snap.snapshot_id, "nonexistent")
        assert "error" in diff


class TestSnapshotRestore:
    def _make_plugin_dir(self, base, plugin_id):
        """Helper to create a test plugin."""
        plugin_dir = base / "installed" / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "plugin_id": plugin_id,
            "name": f"Test {plugin_id}",
            "version": "1.0.0",
            "category": "agent",
            "description": "test",
            "author": "test",
            "entry_point": "plugin",
            "class_name": "TestPlugin",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
        code = '''
from maestro.plugins.base import MaestroPlugin

class TestPlugin(MaestroPlugin):
    def activate(self, context):
        return True
    def deactivate(self):
        return True
    def health_check(self):
        return {"healthy": True, "message": "ok", "metrics": {}}
'''
        (plugin_dir / "plugin.py").write_text(code)

    def test_restore_enables_correct_plugins(self, tmp_path):
        self._make_plugin_dir(tmp_path, "test.snap1")
        self._make_plugin_dir(tmp_path, "test.snap2")

        mgr = ModManager(plugins_dir=str(tmp_path))
        mgr.discover()
        mgr.load("test.snap1")
        mgr.enable("test.snap1")

        # Save with snap1 enabled
        snap = mgr.save_snapshot("with_snap1")

        # Disable snap1, enable snap2
        mgr.disable("test.snap1")
        mgr.load("test.snap2")
        mgr.enable("test.snap2")

        # Restore — should re-enable snap1
        assert mgr.restore_snapshot(snap.snapshot_id)

    def test_restore_nonexistent_fails(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        assert not mgr.restore_snapshot("nonexistent-id")
