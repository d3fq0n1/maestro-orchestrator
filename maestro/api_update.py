"""
API endpoints for the auto-updater.

GET  /api/update/check    — check if updates are available
POST /api/update/apply    — pull latest changes
GET  /api/update/remote   — get configured remote URL
PUT  /api/update/remote   — set the remote URL
POST /api/update/restart  — restart the server process
"""

import os
import shutil
import signal
import sys

from fastapi import APIRouter
from pydantic import BaseModel, Field
from maestro.updater import check_for_updates, apply_update
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


@router.get("/check")
async def update_check():
    """Check the remote for new commits."""
    if not _has_git():
        return _NOT_AVAILABLE
    try:
        return check_for_updates()
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
        return apply_update()
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
    # Send SIGHUP to PID 1 (Docker entrypoint) so the container restarts,
    # or fall back to terminating the current process which triggers
    # Docker's restart policy (restart: unless-stopped).
    try:
        os.kill(1, signal.SIGTERM)
    except OSError:
        os.kill(os.getpid(), signal.SIGTERM)
    return {"restarting": True}
