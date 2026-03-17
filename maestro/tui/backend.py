"""
Backend abstraction for the Maestro TUI.

Supports two connection modes:
  - Direct import (in-process): imports orchestrator modules directly.
    Best for single-device setups where the TUI and backend share a process.
  - HTTP client: connects to a running Maestro FastAPI server via localhost.
    Consumes the SSE streaming endpoint for progressive updates.
    Best for multi-device clusters or when the server runs separately.

Usage:
    backend = create_backend(mode="direct")  # or "http"
    async for event in backend.orchestrate("prompt"):
        ...  # handle events
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class TUIEvent:
    """Normalized event emitted by both backend modes."""
    kind: str          # "stage", "agent_response", "agents_done", "dissent",
                       # "ncg", "consensus", "r2", "done", "error",
                       # "node_list", "key_status"
    data: dict = field(default_factory=dict)


class MaestroBackend(ABC):
    """Abstract base for TUI backend connections."""

    @abstractmethod
    async def orchestrate(
        self,
        prompt: str,
        deliberation_enabled: bool = True,
        deliberation_rounds: int = 1,
    ) -> AsyncIterator[TUIEvent]:
        """Run orchestration and yield progressive events."""
        ...

    @abstractmethod
    async def list_nodes(self) -> list[dict]:
        """Return registered storage nodes."""
        ...

    @abstractmethod
    async def list_keys(self) -> list[dict]:
        """Return API key configuration status."""
        ...

    @abstractmethod
    async def get_session_history(self, limit: int = 20) -> list[dict]:
        """Return recent session summaries."""
        ...

    async def get_discovery_status(self) -> dict:
        """Return LAN shard discovery status. Override in subclasses."""
        return {}


class DirectBackend(MaestroBackend):
    """In-process backend — imports orchestrator modules directly."""

    def __init__(self):
        _bootstrap_paths()
        _load_env()

    async def orchestrate(
        self,
        prompt: str,
        deliberation_enabled: bool = True,
        deliberation_rounds: int = 1,
    ) -> AsyncIterator[TUIEvent]:
        from maestro.agents.sol import Sol
        from maestro.agents.aria import Aria
        from maestro.agents.prism import Prism
        from maestro.agents.tempagent import TempAgent
        from maestro.orchestrator import run_orchestration_stream
        from maestro.ncg.generator import (
            OpenAIHeadlessGenerator,
            AnthropicHeadlessGenerator,
            MockHeadlessGenerator,
        )

        agents = [Sol(), Aria(), Prism(), TempAgent()]
        generator = _select_headless_generator()

        async for raw_event in run_orchestration_stream(
            prompt=prompt,
            agents=agents,
            ncg_enabled=True,
            session_logging=True,
            headless_generator=generator,
            deliberation_enabled=deliberation_enabled,
            deliberation_rounds=deliberation_rounds,
        ):
            parsed = _parse_sse(raw_event)
            if parsed:
                yield parsed

    async def list_nodes(self) -> list[dict]:
        from maestro.shard_registry import StorageNodeRegistry
        from dataclasses import asdict
        registry = StorageNodeRegistry()
        return [asdict(n) for n in registry.list_nodes()]

    async def list_keys(self) -> list[dict]:
        from maestro.keyring import list_keys
        return [
            {"label": s.label, "configured": s.configured, "masked": s.masked_value}
            for s in list_keys()
        ]

    async def get_session_history(self, limit: int = 20) -> list[dict]:
        from maestro.session import SessionLogger
        logger = SessionLogger()
        return logger.list_sessions(limit=limit)


class HTTPBackend(MaestroBackend):
    """HTTP client backend — connects to a running Maestro server."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self._base_url = base_url.rstrip("/")

    async def orchestrate(
        self,
        prompt: str,
        deliberation_enabled: bool = True,
        deliberation_rounds: int = 1,
    ) -> AsyncIterator[TUIEvent]:
        import httpx

        url = f"{self._base_url}/api/ask/stream"
        payload = {
            "prompt": prompt,
            "deliberation_enabled": deliberation_enabled,
            "deliberation_rounds": deliberation_rounds,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST", url, json=payload,
            ) as response:
                response.raise_for_status()
                event_type = None
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        event_type = None
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:") and event_type:
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            data = {"raw": line[5:].strip()}
                        yield TUIEvent(kind=event_type, data=data)

    async def list_nodes(self) -> list[dict]:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{self._base_url}/api/storage/nodes")
            resp.raise_for_status()
            return resp.json().get("nodes", [])

    async def list_keys(self) -> list[dict]:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{self._base_url}/api/keys")
            resp.raise_for_status()
            return resp.json().get("keys", [])

    async def get_session_history(self, limit: int = 20) -> list[dict]:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(
                f"{self._base_url}/api/sessions", params={"limit": limit},
            )
            resp.raise_for_status()
            return resp.json().get("sessions", [])

    async def get_discovery_status(self) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{self._base_url}/api/storage/discovery")
            resp.raise_for_status()
            return resp.json()


def create_backend(mode: str = "direct", base_url: str = "http://localhost:8000") -> MaestroBackend:
    """Factory: create the appropriate backend based on mode."""
    if mode == "http":
        return HTTPBackend(base_url=base_url)
    return DirectBackend()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap_paths():
    """Ensure maestro and backend packages are importable."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(here))
    backend_dir = os.path.join(project_root, "backend")
    for p in (project_root, backend_dir):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_env():
    """Load .env using the same candidate-path logic as keyring._default_env_path.

    Tries paths in priority order and stops at the first existing file so that
    keys saved by the setup wizard (which also uses _default_env_path) are
    always found on the next TUI launch — regardless of whether the user is
    running from the project root, inside Docker, or with MAESTRO_ENV_FILE set.

    Previously this function only tried ``backend/.env``.  If the wizard saved
    keys to ``project_root/.env`` (the fallback when ``backend/.env`` didn't
    exist), they would not be loaded on restart, causing the TUI to report
    "No API keys configured" even though keys were present on disk.
    """
    from dotenv import load_dotenv
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(here))
    backend_dir = os.path.join(project_root, "backend")

    env_file_var = os.environ.get("MAESTRO_ENV_FILE", "").strip()
    candidates = [
        env_file_var if env_file_var else None,
        os.path.join(backend_dir, ".env"),
        os.path.join(project_root, ".env"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            load_dotenv(dotenv_path=path, override=True)
            return


def _select_headless_generator():
    """Pick the best available headless generator based on API keys."""
    from maestro.ncg.generator import (
        OpenAIHeadlessGenerator,
        AnthropicHeadlessGenerator,
        MockHeadlessGenerator,
    )
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIHeadlessGenerator()
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicHeadlessGenerator()
    return MockHeadlessGenerator()


def _parse_sse(raw: str) -> TUIEvent | None:
    """Parse a raw SSE string into a TUIEvent."""
    event_type = None
    data_str = None
    for line in raw.strip().split("\n"):
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_str = line[5:].strip()
    if event_type and data_str:
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            data = {"raw": data_str}
        return TUIEvent(kind=event_type, data=data)
    return None
