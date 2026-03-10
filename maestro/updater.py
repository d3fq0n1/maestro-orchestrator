#!/usr/bin/env python3
"""
Maestro-Orchestrator Auto-Updater.

Checks the remote Git repository for new commits and pulls updates
automatically, with optional Docker rebuild support.

Works in two modes:
  1. **Git mode** — the project root contains a `.git` directory (local dev).
  2. **Docker mode** — no `.git` dir; uses a VERSION file + `git ls-remote`.

Usage:
    from maestro.updater import check_for_updates, apply_update

Environment variables:
    MAESTRO_AUTO_UPDATE=1       Enable automatic update check on startup
    MAESTRO_UPDATE_BRANCH=main  Branch to track (default: current branch or main)
    MAESTRO_UPDATE_REMOTE=URL   Git remote URL (overrides origin; required in Docker)
"""

import os
import shutil
import subprocess
import sys
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERSION_FILE = os.path.join(_PROJECT_ROOT, "VERSION")


def _is_git_repo() -> bool:
    """Return True if the project root is inside a git repository."""
    return os.path.isdir(os.path.join(_PROJECT_ROOT, ".git"))


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command in the project root directory."""
    return subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _get_remote_url() -> str:
    """Return the configured remote URL, or empty string."""
    return os.environ.get("MAESTRO_UPDATE_REMOTE", "").strip()


def _get_branch() -> str:
    """Return the branch to track."""
    explicit = os.environ.get("MAESTRO_UPDATE_BRANCH", "").strip()
    if explicit:
        return explicit
    if _is_git_repo():
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if result.returncode == 0:
            return result.stdout.strip()
    return "main"


# ── Local commit ──────────────────────────────────────────────────────

def get_local_commit() -> str:
    """Return the current local HEAD commit hash, or empty string if unknown."""
    # Git mode
    if _is_git_repo():
        result = _run(["git", "rev-parse", "HEAD"])
        if result.returncode == 0:
            return result.stdout.strip()
    # Docker mode — read baked-in VERSION file
    if os.path.isfile(_VERSION_FILE):
        with open(_VERSION_FILE) as f:
            value = f.read().strip()
            # The Dockerfile defaults GIT_COMMIT to "unknown"; treat that as empty.
            if value and value.lower() != "unknown":
                return value
    return ""


# ── Remote commit ─────────────────────────────────────────────────────

def get_remote_commit(branch: str | None = None) -> tuple[str, str]:
    """
    Return (remote_commit_hash, error_message).

    Uses `git ls-remote` which does NOT require a local .git directory.
    """
    branch = branch or _get_branch()
    url = _get_remote_url()

    if _is_git_repo() and not url:
        # Dev mode — use normal fetch
        fetch = _run(["git", "fetch", "origin", branch])
        if fetch.returncode != 0:
            return "", fetch.stderr.strip() or "git fetch failed"
        result = _run(["git", "rev-parse", f"origin/{branch}"])
        return (result.stdout.strip() if result.returncode == 0 else ""), ""

    if not url:
        return "", "No remote URL configured."

    # Docker mode — ls-remote works without a local repo
    result = subprocess.run(
        ["git", "ls-remote", url, f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        err = result.stderr.strip() or "git ls-remote failed"
        return "", err
    line = result.stdout.strip()
    if not line:
        return "", f"Branch '{branch}' not found on remote."
    commit = line.split()[0]
    return commit, ""


# ── Commit log ────────────────────────────────────────────────────────

def get_commit_log(local: str, remote: str, branch: str | None = None) -> list[str]:
    """Return one-line summaries of commits between local..remote."""
    if not local or not remote or local == remote:
        return []

    # Git mode — direct log
    if _is_git_repo():
        result = _run(["git", "log", "--oneline", f"{local}..{remote}"])
        if result.returncode == 0:
            return [l for l in result.stdout.strip().splitlines() if l]

    # Docker mode — shallow clone to read log
    url = _get_remote_url()
    if not url:
        return []
    branch = branch or _get_branch()
    try:
        with tempfile.TemporaryDirectory(prefix="maestro_update_") as tmp:
            clone = subprocess.run(
                ["git", "clone", "--bare", "--filter=blob:none",
                 "--single-branch", "--branch", branch, url, tmp],
                capture_output=True, text=True, timeout=60,
            )
            if clone.returncode != 0:
                return []
            log = subprocess.run(
                ["git", "--git-dir", tmp, "log", "--oneline", f"{local}..{remote}"],
                capture_output=True, text=True, timeout=15,
            )
            if log.returncode == 0:
                return [l for l in log.stdout.strip().splitlines() if l]
    except Exception:
        pass
    return []


# ── Check ─────────────────────────────────────────────────────────────

def check_for_updates(branch: str | None = None) -> dict:
    """
    Check if updates are available from the remote.

    Returns a dict with:
        available (bool): True if remote is ahead of local
        local_commit (str): Current local commit hash (short)
        remote_commit (str): Latest remote commit hash (short)
        new_commits (list[str]): One-line summaries of new commits
        branch (str): Branch being tracked
        error (str, optional): Error message if check failed
    """
    branch = branch or _get_branch()
    local = get_local_commit()
    remote, fetch_err = get_remote_commit(branch)

    if not remote:
        url = _get_remote_url()
        if not url:
            msg = "No remote configured. Set your repository URL above, then check for updates."
        elif fetch_err:
            msg = fetch_err
        else:
            msg = "Could not determine remote commit."
        return {
            "available": False,
            "local_commit": local[:8] if local else "",
            "remote_commit": "",
            "new_commits": [],
            "branch": branch,
            "error": msg,
        }

    # If local commit is unknown, we can't compare — recommend updating.
    if not local:
        return {
            "available": True,
            "local_commit": "",
            "local_unknown": True,
            "remote_commit": remote[:8],
            "new_commits": [],
            "branch": branch,
        }

    available = local != remote
    new_commits = get_commit_log(local, remote, branch) if available else []

    return {
        "available": available,
        "local_commit": local[:8] if local else "",
        "remote_commit": remote[:8],
        "new_commits": new_commits,
        "branch": branch,
    }


# ── Apply ─────────────────────────────────────────────────────────────

def has_local_changes() -> bool:
    """Return True if there are uncommitted changes in the working tree."""
    if not _is_git_repo():
        return False
    result = _run(["git", "status", "--porcelain"])
    return bool(result.stdout.strip()) if result.returncode == 0 else False


def apply_update(branch: str | None = None, rebuild: bool = False) -> dict:
    """
    Pull the latest changes and optionally rebuild Docker.

    In git mode: does a normal `git pull`.
    In Docker mode: clones into a temp dir and copies updated files over.

    Returns a dict with:
        success (bool): Whether the update succeeded
        message (str): Human-readable result message
        commits_pulled (int): Number of new commits pulled
        rebuilt (bool): Whether Docker was rebuilt
    """
    branch = branch or _get_branch()

    if _is_git_repo():
        return _apply_git_mode(branch, rebuild)
    return _apply_docker_mode(branch, rebuild)


def _apply_git_mode(branch: str, rebuild: bool) -> dict:
    """Pull updates in a normal git working tree."""
    url = _get_remote_url()
    if url:
        _run(["git", "remote", "set-url", "origin", url])

    if has_local_changes():
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
    new_commits = get_commit_log(before, after, branch) if before != after else []

    if stashed:
        _run(["git", "stash", "pop"])

    rebuilt = _maybe_rebuild(rebuild, new_commits)
    count = len(new_commits)
    msg = "Already up to date." if count == 0 else f"Updated successfully — {count} new commit{'s' if count != 1 else ''}."

    return {
        "success": True,
        "message": msg,
        "commits_pulled": count,
        "rebuilt": rebuilt,
    }


# Directories to sync from a fresh clone into the running container.
_SYNC_DIRS = ["maestro", "backend"]


def _apply_docker_mode(branch: str, rebuild: bool) -> dict:
    """Clone into a temp dir and copy updated files into the running container."""
    url = _get_remote_url()
    if not url:
        return {
            "success": False,
            "message": "No remote URL configured.",
            "commits_pulled": 0,
            "rebuilt": False,
        }

    before = get_local_commit()

    try:
        tmp = tempfile.mkdtemp(prefix="maestro_update_")
        clone = subprocess.run(
            ["git", "clone", "--depth=50", "--single-branch",
             "--branch", branch, url, tmp],
            capture_output=True, text=True, timeout=120,
        )
        if clone.returncode != 0:
            return {
                "success": False,
                "message": f"Clone failed: {clone.stderr.strip()}",
                "commits_pulled": 0,
                "rebuilt": False,
            }

        # Read the new HEAD
        head = subprocess.run(
            ["git", "-C", tmp, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        after = head.stdout.strip() if head.returncode == 0 else ""

        if before and before == after:
            shutil.rmtree(tmp, ignore_errors=True)
            return {
                "success": True,
                "message": "Already up to date.",
                "commits_pulled": 0,
                "rebuilt": False,
            }

        # Get commit log from the clone
        new_commits: list[str] = []
        if before and after:
            log = subprocess.run(
                ["git", "-C", tmp, "log", "--oneline", f"{before}..{after}"],
                capture_output=True, text=True,
            )
            if log.returncode == 0:
                new_commits = [l for l in log.stdout.strip().splitlines() if l]

        # Copy updated directories into the running app, preserving
        # user-created files like .env (which stores API keys).
        for d in _SYNC_DIRS:
            src = os.path.join(tmp, d)
            dst = os.path.join(_PROJECT_ROOT, d)
            if os.path.isdir(src):
                _sync_directory(src, dst)

        # Update VERSION file so next check knows where we are
        with open(_VERSION_FILE, "w") as f:
            f.write(after + "\n")

        shutil.rmtree(tmp, ignore_errors=True)

    except Exception as exc:
        return {
            "success": False,
            "message": f"Update failed: {exc}",
            "commits_pulled": 0,
            "rebuilt": False,
        }

    rebuilt = _maybe_rebuild(rebuild, new_commits)
    count = len(new_commits) or (1 if before != after else 0)
    msg = f"Updated successfully — {count} new commit{'s' if count != 1 else ''}. Restart the container to load changes."

    return {
        "success": True,
        "message": msg,
        "commits_pulled": count,
        "rebuilt": rebuilt,
    }


# ── Helpers ───────────────────────────────────────────────────────────

# Files in synced directories that must survive an update.
_PRESERVE_PATTERNS = {".env", ".env.local"}


def _sync_directory(src: str, dst: str) -> None:
    """Replace *dst* with *src*, preserving user-created files like `.env`."""
    preserved: dict[str, bytes] = {}
    if os.path.isdir(dst):
        for name in _PRESERVE_PATTERNS:
            path = os.path.join(dst, name)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    preserved[name] = f.read()
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    for name, data in preserved.items():
        with open(os.path.join(dst, name), "wb") as f:
            f.write(data)


def _maybe_rebuild(rebuild: bool, new_commits: list) -> bool:
    if not rebuild or not new_commits:
        return False
    compose = _find_compose_cmd()
    if not compose:
        return False
    print("  Rebuilding Docker image ...")
    build_result = subprocess.run(
        compose + ["up", "-d", "--build"],
        cwd=_PROJECT_ROOT,
    )
    return build_result.returncode == 0


def _find_compose_cmd() -> list[str]:
    """Return the Docker Compose command as a list, or empty if not found."""
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
