"""
API endpoints for the auto-updater.

GET  /api/update/check    -- check if updates are available
POST /api/update/apply    -- pull latest changes
GET  /api/update/remote   -- get configured remote URL
PUT  /api/update/remote   -- set the remote URL
POST /api/update/restart  -- restart the server process
GET  /api/update/auto     -- get auto-updater status
PUT  /api/update/auto     -- configure auto-updater settings
GET  /api/update/stream   -- SSE stream of real-time update events
"""

import asyncio
import json
import os
import shutil
import signal
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from maestro.updater import (
    check_for_updates,
    apply_update,
    get_auto_updater,
    UpdateEvent,
)
from maestro.keyring import _default_env_path, _upsert_env_file

router = APIRouter(prefix="/api/update", tags=["update"])

_NOT_AVAILABLE = {
    "available": False,
    "local_commit": "",
    "remote_commit": "",
    "new_commits": [],
    "branch": "",
    "git_missing": True,
}


def _has_git() -> bool:
    return shutil.which("git") is not None


# ── Existing endpoints (unchanged behavior) ──────────────────────

@router.get("/check")
async def update_check():
    """Check the remote for new commits."""
    if not _has_git():
        return _NOT_AVAILABLE
    try:
        updater = get_auto_updater()
        info = await updater.trigger_check()
        return info
    except Exception as e:
        return {
            "available": False,
            "error": f"Update check failed: {e}",
            "local_commit": "",
            "remote_commit": "",
            "new_commits": [],
            "branch": "",
        }


@router.post("/apply")
async def update_apply():
    """Pull latest changes from the remote."""
    if not _has_git():
        return {"success": False, "message": "Git is not available.", "commits_pulled": 0, "rebuilt": False}
    try:
        updater = get_auto_updater()
        return await updater.trigger_apply()
    except Exception as e:
        return {"success": False, "message": str(e), "commits_pulled": 0, "rebuilt": False}


_REMOTE_ENV_VAR = "MAESTRO_UPDATE_REMOTE"


class SetRemoteRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)


@router.get("/remote")
async def get_remote():
    """Return the currently configured remote URL."""
    url = os.environ.get(_REMOTE_ENV_VAR, "").strip()
    return {"url": url, "configured": bool(url)}


@router.put("/remote")
async def set_remote(body: SetRemoteRequest):
    """Set the remote repository URL (persisted to .env)."""
    url = body.url.strip()
    # Persist to .env file
    _upsert_env_file(_default_env_path(), _REMOTE_ENV_VAR, url)
    # Reflect into current process
    os.environ[_REMOTE_ENV_VAR] = url
    return {"url": url, "configured": True}


@router.post("/restart")
async def restart_server():
    """Restart the server process by re-executing the entrypoint."""
    try:
        os.kill(1, signal.SIGTERM)
    except OSError:
        os.kill(os.getpid(), signal.SIGTERM)
    return {"restarting": True}


# ── Auto-updater configuration ───────────────────────────────────

class AutoUpdateConfig(BaseModel):
    enabled: bool | None = None
    poll_interval: int | None = Field(None, ge=10, le=3600)
    auto_apply: bool | None = None


@router.get("/auto")
async def get_auto_status():
    """Return auto-updater status and configuration."""
    updater = get_auto_updater()
    return updater.status()


@router.put("/auto")
async def configure_auto(body: AutoUpdateConfig):
    """Update auto-updater settings on the fly."""
    updater = get_auto_updater()
    result = updater.configure(
        enabled=body.enabled,
        poll_interval=body.poll_interval,
        auto_apply=body.auto_apply,
    )

    # Persist the enabled state to .env so it survives restarts
    env_path = _default_env_path()
    if body.enabled is not None:
        _upsert_env_file(env_path, "MAESTRO_AUTO_UPDATE", "1" if body.enabled else "0")
        os.environ["MAESTRO_AUTO_UPDATE"] = "1" if body.enabled else "0"
    if body.poll_interval is not None:
        _upsert_env_file(env_path, "MAESTRO_UPDATE_INTERVAL", str(body.poll_interval))
        os.environ["MAESTRO_UPDATE_INTERVAL"] = str(body.poll_interval)
    if body.auto_apply is not None:
        _upsert_env_file(env_path, "MAESTRO_AUTO_APPLY_UPDATES", "1" if body.auto_apply else "0")
        os.environ["MAESTRO_AUTO_APPLY_UPDATES"] = "1" if body.auto_apply else "0"

    # Ensure the background task is running if enabled
    if result.get("enabled") and not result.get("running"):
        await updater.start()

    return result


# ── SSE stream for real-time update events ───────────────────────

@router.get("/stream")
async def update_stream():
    """Server-Sent Events stream of auto-updater notifications.

    Clients receive events as they happen: check, available, applying,
    applied, error, up_to_date.  A heartbeat (: keepalive) is sent
    every 15 seconds to prevent connection drops.
    """

    async def event_generator():
        queue: asyncio.Queue[UpdateEvent] = asyncio.Queue()

        def _listener(event: UpdateEvent):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        updater = get_auto_updater()
        updater.on_event(_listener)

        # Send initial status immediately
        status = updater.status()
        yield f"event: status\ndata: {json.dumps(status)}\n\n"

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = {
                        "kind": event.kind,
                        "data": event.data,
                        "timestamp": event.timestamp,
                    }
                    yield f"event: {event.kind}\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive
                    yield ": keepalive\n\n"
        finally:
            updater.remove_listener(_listener)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
