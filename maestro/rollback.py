"""
Rollback & Snapshot System — reversibility guarantee for code injection.

Every injection the CodeInjector performs is paired with a snapshot of
the original state.  The RollbackLog is an append-only ledger that
records what was changed, what the original value was, and whether the
change has been reverted.

Three snapshot types:
  1. runtime  — stores the previous in-memory value of a module variable
  2. source   — copies the original file content to data/rollbacks/<id>.bak
  3. config   — snapshots the runtime config overlay before mutation

Rollback is always one call away: `RollbackLog.rollback(rollback_id)` or
`RollbackLog.rollback_cycle(cycle_id)` to undo everything from a cycle.
"""

import json
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_DEFAULT_ROLLBACK_DIR = Path(__file__).resolve().parent.parent / "data" / "rollbacks"


@dataclass
class RollbackEntry:
    """Record of a single injected change and how to undo it."""
    rollback_id: str
    proposal_id: str
    cycle_id: str
    injection_type: str          # "runtime", "source_patch", "config"
    module_name: str
    target_name: str
    original_value: str
    new_value: str
    file_path: Optional[str] = None   # only for source_patch
    backup_path: Optional[str] = None # path to .bak file for source patches
    status: str = "applied"           # "applied" | "rolled_back"
    timestamp: str = ""
    rolled_back_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class RollbackLog:
    """
    Append-only ledger of all injected changes with snapshot data.

    Persists to ``data/rollbacks/log.json``.  Each entry contains enough
    information to fully restore the previous state — whether that means
    setting a module variable back, restoring a source file from backup,
    or reverting a config overlay key.
    """

    def __init__(self, rollback_dir: str = None):
        self._dir = Path(rollback_dir) if rollback_dir else _DEFAULT_ROLLBACK_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._dir / "log.json"
        self._entries: list[dict] = self._load()

    # --- persistence helpers ---

    def _load(self) -> list[dict]:
        if self._log_path.exists():
            try:
                return json.loads(self._log_path.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save(self):
        self._log_path.write_text(json.dumps(self._entries, indent=2, default=str))

    # --- public API ---

    def snapshot_runtime(
        self,
        proposal_id: str,
        cycle_id: str,
        module_name: str,
        target_name: str,
        original_value: str,
        new_value: str,
    ) -> RollbackEntry:
        """Record a runtime parameter change (in-memory variable)."""
        entry = RollbackEntry(
            rollback_id=str(uuid.uuid4()),
            proposal_id=proposal_id,
            cycle_id=cycle_id,
            injection_type="runtime",
            module_name=module_name,
            target_name=target_name,
            original_value=original_value,
            new_value=new_value,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(asdict(entry))
        self._save()
        return entry

    def snapshot_source(
        self,
        proposal_id: str,
        cycle_id: str,
        module_name: str,
        target_name: str,
        file_path: str,
        original_value: str,
        new_value: str,
    ) -> RollbackEntry:
        """
        Record a source-file patch.  Copies the original file to a .bak
        in the rollback directory before returning.
        """
        rollback_id = str(uuid.uuid4())
        backup_path = str(self._dir / f"{rollback_id}.bak")

        src = Path(file_path)
        if src.exists():
            shutil.copy2(str(src), backup_path)

        entry = RollbackEntry(
            rollback_id=rollback_id,
            proposal_id=proposal_id,
            cycle_id=cycle_id,
            injection_type="source_patch",
            module_name=module_name,
            target_name=target_name,
            original_value=original_value,
            new_value=new_value,
            file_path=file_path,
            backup_path=backup_path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(asdict(entry))
        self._save()
        return entry

    def snapshot_config(
        self,
        proposal_id: str,
        cycle_id: str,
        module_name: str,
        target_name: str,
        original_value: str,
        new_value: str,
    ) -> RollbackEntry:
        """Record a config overlay change."""
        entry = RollbackEntry(
            rollback_id=str(uuid.uuid4()),
            proposal_id=proposal_id,
            cycle_id=cycle_id,
            injection_type="config",
            module_name=module_name,
            target_name=target_name,
            original_value=original_value,
            new_value=new_value,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(asdict(entry))
        self._save()
        return entry

    # --- rollback ---

    def mark_rolled_back(self, rollback_id: str) -> bool:
        """Mark a single entry as rolled back.  Returns False if not found."""
        for entry in self._entries:
            if entry["rollback_id"] == rollback_id and entry["status"] == "applied":
                entry["status"] = "rolled_back"
                entry["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    # --- queries ---

    def get(self, rollback_id: str) -> Optional[dict]:
        for entry in self._entries:
            if entry["rollback_id"] == rollback_id:
                return entry
        return None

    def get_active(self) -> list[dict]:
        """All entries whose status is 'applied' (not yet rolled back)."""
        return [e for e in self._entries if e["status"] == "applied"]

    def get_by_cycle(self, cycle_id: str) -> list[dict]:
        """All entries (active or not) for a given improvement cycle."""
        return [e for e in self._entries if e["cycle_id"] == cycle_id]

    def get_active_by_cycle(self, cycle_id: str) -> list[dict]:
        """Active (non-rolled-back) entries for a cycle."""
        return [
            e for e in self._entries
            if e["cycle_id"] == cycle_id and e["status"] == "applied"
        ]

    def list_all(self, limit: int = 50) -> list[dict]:
        """Recent entries, newest first."""
        return list(reversed(self._entries[-limit:]))

    def count_active(self) -> int:
        return sum(1 for e in self._entries if e["status"] == "applied")
