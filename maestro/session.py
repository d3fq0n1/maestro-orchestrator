"""
Session History Logger — Persistent record of every orchestration session.

Every time the council convenes, the session logger captures the full record:
prompt, agent responses, NCG drift report, consensus output, and metadata.
This is the data layer that dissent analysis and R2 operate on. Without
session history, those modules have nothing to analyze across time.

Storage is file-based JSON: one file per session in data/sessions/. No
database dependency, stays lightweight, and the files are human-readable
for manual inspection or external tooling.
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


# Default storage directory, relative to project root
_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"


@dataclass
class SessionRecord:
    """Complete record of a single orchestration session."""
    session_id: str
    timestamp: str
    prompt: str
    agent_responses: dict          # {agent_name: response_text}
    consensus: dict                # aggregated output from aggregate_responses
    ncg_benchmark: dict = field(default_factory=dict)  # from ncg_drift_report, if enabled
    agents_used: list = field(default_factory=list)     # names of agents in the council
    ncg_enabled: bool = True
    metadata: dict = field(default_factory=dict)        # extensible: latency, model versions, etc.


class SessionLogger:
    """
    Writes and reads orchestration session records.

    Each session is stored as a single JSON file named by session ID.
    The logger handles serialization and provides query methods that
    dissent analysis and R2 will use to look across sessions.
    """

    def __init__(self, storage_dir: str = None):
        self._dir = Path(storage_dir) if storage_dir else _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def storage_dir(self) -> Path:
        return self._dir

    def save(self, record: SessionRecord) -> Path:
        """
        Persist a session record to disk.

        Returns the path to the written file.
        """
        filepath = self._dir / f"{record.session_id}.json"
        data = asdict(record)
        filepath.write_text(json.dumps(data, indent=2, default=str))
        return filepath

    def load(self, session_id: str) -> SessionRecord:
        """
        Load a single session by ID.

        Raises FileNotFoundError if the session doesn't exist.
        Raises json.JSONDecodeError if the file is corrupted.
        """
        filepath = self._dir / f"{session_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        data = json.loads(filepath.read_text())
        return SessionRecord(**data)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list:
        """
        List stored sessions, most recent first.

        Returns a list of summary dicts (id, timestamp, prompt preview,
        agent count) without loading full response content.
        """
        files = sorted(self._dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        summaries = []
        for f in files[offset:offset + limit]:
            try:
                data = json.loads(f.read_text())
                summaries.append({
                    "session_id": data["session_id"],
                    "timestamp": data["timestamp"],
                    "prompt": data["prompt"][:120],
                    "agent_count": len(data.get("agent_responses", {})),
                    "ncg_enabled": data.get("ncg_enabled", False),
                    "silent_collapse": data.get("ncg_benchmark", {}).get("silent_collapse", False),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return summaries

    def list_all_ids(self) -> list:
        """Return all session IDs, most recent first."""
        files = sorted(self._dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        return [f.stem for f in files]

    def delete(self, session_id: str) -> bool:
        """Remove a session record. Returns True if deleted, False if not found."""
        filepath = self._dir / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def count(self) -> int:
        """Total number of stored sessions."""
        return len(list(self._dir.glob("*.json")))


def build_session_record(
    prompt: str,
    agent_responses: dict,
    final_output: dict,
    ncg_enabled: bool = True,
    agents_used: list = None,
    metadata: dict = None,
) -> SessionRecord:
    """
    Convenience function to construct a SessionRecord from orchestration
    results. Called by the orchestrator after aggregation completes.
    """
    ncg_benchmark = final_output.get("ncg_benchmark", {})

    return SessionRecord(
        session_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        prompt=prompt,
        agent_responses=agent_responses,
        consensus=final_output,
        ncg_benchmark=ncg_benchmark,
        agents_used=agents_used or list(agent_responses.keys()),
        ncg_enabled=ncg_enabled,
        metadata=metadata or {},
    )
