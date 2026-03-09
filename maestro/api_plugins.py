"""
API routes for the mod manager (plugin system) and weight state snapshots.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from maestro.plugins.manager import ModManager

router = APIRouter(prefix="/api", tags=["plugins"])

# Shared instance
_manager: Optional[ModManager] = None


def _get_manager() -> ModManager:
    global _manager
    if _manager is None:
        _manager = ModManager()
        _manager.discover()
    return _manager


# --- Request models ---

class PluginConfigUpdate(BaseModel):
    config: dict = Field(default_factory=dict)


class SnapshotCreate(BaseModel):
    name: str
    description: str = ""


# --- Plugin endpoints ---

@router.get("/plugins")
async def list_plugins():
    manager = _get_manager()
    return {"plugins": manager.list_plugins()}


@router.post("/plugins/discover")
async def discover_plugins():
    manager = _get_manager()
    manifests = manager.discover()
    return {
        "discovered": len(manifests),
        "plugins": [
            {"plugin_id": m.plugin_id, "name": m.name, "version": m.version}
            for m in manifests
        ],
    }


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str):
    manager = _get_manager()
    if not manager.load(plugin_id):
        raise HTTPException(status_code=400, detail=f"Failed to load plugin: {plugin_id}")
    if not manager.enable(plugin_id):
        raise HTTPException(status_code=400, detail=f"Failed to enable plugin: {plugin_id}")
    return {"status": "enabled", "plugin_id": plugin_id}


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    manager = _get_manager()
    if not manager.disable(plugin_id):
        raise HTTPException(status_code=400, detail=f"Failed to disable plugin: {plugin_id}")
    return {"status": "disabled", "plugin_id": plugin_id}


@router.post("/plugins/{plugin_id}/reload")
async def reload_plugin(plugin_id: str):
    manager = _get_manager()
    if not manager.reload(plugin_id):
        raise HTTPException(status_code=400, detail=f"Failed to reload plugin: {plugin_id}")
    return {"status": "reloaded", "plugin_id": plugin_id}


@router.get("/plugins/{plugin_id}")
async def get_plugin_info(plugin_id: str):
    manager = _get_manager()
    info = manager.get_plugin_info(plugin_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    return info


@router.put("/plugins/{plugin_id}/config")
async def update_plugin_config(plugin_id: str, update: PluginConfigUpdate):
    manager = _get_manager()
    if not manager.update_plugin_config(plugin_id, update.config):
        raise HTTPException(status_code=400, detail="Config update failed")
    return {"status": "updated", "plugin_id": plugin_id}


@router.get("/plugins/health")
async def plugins_health():
    manager = _get_manager()
    return {"health": manager.health_check_all()}


# --- Snapshot endpoints ---

@router.get("/snapshots")
async def list_snapshots():
    manager = _get_manager()
    return {"snapshots": manager.list_snapshots()}


@router.post("/snapshots")
async def create_snapshot(req: SnapshotCreate):
    manager = _get_manager()
    snap = manager.save_snapshot(req.name, req.description)
    return {
        "snapshot_id": snap.snapshot_id,
        "name": snap.name,
        "created_at": snap.created_at,
    }


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str):
    manager = _get_manager()
    if not manager.restore_snapshot(snapshot_id):
        raise HTTPException(status_code=400, detail="Snapshot restore failed")
    return {"status": "restored", "snapshot_id": snapshot_id}


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    manager = _get_manager()
    data = manager.load_snapshot(snapshot_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")
    return data


@router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    manager = _get_manager()
    if not manager.delete_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")
    return {"status": "deleted", "snapshot_id": snapshot_id}


@router.get("/snapshots/diff/{a}/{b}")
async def diff_snapshots(a: str, b: str):
    manager = _get_manager()
    return manager.diff_snapshots(a, b)
