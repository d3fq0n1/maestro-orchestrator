#!/usr/bin/env python3
"""
Maestro-Orchestrator Auto-Updater.

Checks the remote Git repository for new commits and pulls updates
automatically, with optional Docker rebuild support.

Usage:
    from maestro.updater import check_for_updates, apply_update

Environment variables:
    MAESTRO_AUTO_UPDATE=1       Enable automatic update check on startup
    MAESTRO_UPDATE_BRANCH=main  Branch to track (default: current branch)
    MAESTRO_UPDATE_REMOTE=URL   Git remote URL (overrides origin; required in Docker)
"""

import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command in the project root directory."""
    return subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        **kwargs,
    )


def get_current_branch() -> str:
    """Return the name of the current Git branch."""
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else "master"


def get_local_commit() -> str:
    """Return the current local HEAD commit hash."""
    result = _run(["git", "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def _sync_remote_url() -> None:
    """If MAESTRO_UPDATE_REMOTE is set, point origin at that URL."""
    url = os.environ.get("MAESTRO_UPDATE_REMOTE", "").strip()
    if url:
        _run(["git", "remote", "set-url", "origin", url])


def get_remote_commit(branch: str | None = None) -> str:
    """Fetch and return the latest remote commit hash for the branch."""
    _sync_remote_url()
    branch = branch or os.environ.get("MAESTRO_UPDATE_BRANCH") or get_current_branch()
    fetch = _run(["git", "fetch", "origin", branch])
    if fetch.returncode != 0:
        return ""
    result = _run(["git", "rev-parse", f"origin/{branch}"])
    return result.stdout.strip() if result.returncode == 0 else ""


def get_commit_log(local: str, remote: str) -> list[str]:
    """Return a list of new commit messages between local and remote."""
    if not local or not remote:
        return []
    result = _run(["git", "log", "--oneline", f"{local}..{remote}"])
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.strip().splitlines() if line]


def check_for_updates(branch: str | None = None) -> dict:
    """
    Check if updates are available from the remote.

    Returns a dict with:
        available (bool): True if remote is ahead of local
        local_commit (str): Current local commit hash (short)
        remote_commit (str): Latest remote commit hash (short)
        new_commits (list[str]): One-line summaries of new commits
        branch (str): Branch being tracked
    """
    branch = branch or os.environ.get("MAESTRO_UPDATE_BRANCH") or get_current_branch()
    local = get_local_commit()
    remote = get_remote_commit(branch)

    if not local or not remote:
        has_remote_configured = bool(os.environ.get("MAESTRO_UPDATE_REMOTE", "").strip())
        if has_remote_configured:
            msg = "Could not reach the remote repository."
        else:
            msg = "No remote configured. Set MAESTRO_UPDATE_REMOTE in your environment or docker-compose.yml."
        return {
            "available": False,
            "local_commit": local[:8] if local else "",
            "remote_commit": "",
            "new_commits": [],
            "branch": branch,
            "error": msg,
        }

    available = local != remote
    new_commits = get_commit_log(local, remote) if available else []

    return {
        "available": available,
        "local_commit": local[:8],
        "remote_commit": remote[:8],
        "new_commits": new_commits,
        "branch": branch,
    }


def has_local_changes() -> bool:
    """Return True if there are uncommitted changes in the working tree."""
    result = _run(["git", "status", "--porcelain"])
    return bool(result.stdout.strip()) if result.returncode == 0 else False


def apply_update(branch: str | None = None, rebuild: bool = False) -> dict:
    """
    Pull the latest changes and optionally rebuild Docker.

    Returns a dict with:
        success (bool): Whether the update succeeded
        message (str): Human-readable result message
        commits_pulled (int): Number of new commits pulled
        rebuilt (bool): Whether Docker was rebuilt
    """
    branch = branch or os.environ.get("MAESTRO_UPDATE_BRANCH") or get_current_branch()

    if has_local_changes():
        # Stash local changes so pull doesn't fail
        _run(["git", "stash", "push", "-m", "maestro-auto-update-stash"])
        stashed = True
    else:
        stashed = False

    before = get_local_commit()
    pull = _run(["git", "pull", "origin", branch])

    if pull.returncode != 0:
        if stashed:
            _run(["git", "stash", "pop"])
        return {
            "success": False,
            "message": f"git pull failed: {pull.stderr.strip()}",
            "commits_pulled": 0,
            "rebuilt": False,
        }

    after = get_local_commit()
    new_commits = get_commit_log(before, after) if before != after else []

    if stashed:
        _run(["git", "stash", "pop"])

    rebuilt = False
    if rebuild and new_commits:
        compose = _find_compose_cmd()
        if compose:
            print("  Rebuilding Docker image ...")
            build_result = subprocess.run(
                compose + ["up", "-d", "--build"],
                cwd=_PROJECT_ROOT,
            )
            rebuilt = build_result.returncode == 0

    count = len(new_commits)
    if count == 0:
        msg = "Already up to date."
    else:
        msg = f"Updated successfully — {count} new commit{'s' if count != 1 else ''}."

    return {
        "success": True,
        "message": msg,
        "commits_pulled": count,
        "rebuilt": rebuilt,
    }


def _find_compose_cmd() -> list[str]:
    """Return the Docker Compose command as a list, or empty if not found."""
    import shutil

    for cmd in [["docker", "compose"], ["docker-compose"]]:
        try:
            result = subprocess.run(
                cmd + ["version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    return []


def startup_check() -> None:
    """
    Run an update check at startup if MAESTRO_AUTO_UPDATE=1.

    Called from entrypoint.py. Non-blocking — prints a notice if updates
    are available but does not apply them automatically.
    """
    if os.environ.get("MAESTRO_AUTO_UPDATE", "").strip() not in ("1", "true", "yes"):
        return

    try:
        info = check_for_updates()
    except Exception:
        return

    if info.get("available"):
        count = len(info.get("new_commits", []))
        print()
        print(f"  [Update] {count} new commit{'s' if count != 1 else ''} available on {info['branch']}.")
        print(f"           Local: {info['local_commit']}  Remote: {info['remote_commit']}")
        print("           Run '/update' in the CLI or 'make update' to apply.")
        print()
