"""
API endpoints for the auto-updater.

GET  /api/update/check   — check if updates are available
POST /api/update/apply   — pull latest changes
"""

import shutil

from fastapi import APIRouter
from maestro.updater import check_for_updates, apply_update

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
