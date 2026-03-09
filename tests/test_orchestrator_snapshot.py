"""
Snapshot tests for orchestrator hot paths.

Captures the structure and behavior of run_orchestration_async and
run_orchestration_stream BEFORE the mod manager hook integration, so we
can verify the pipeline still produces identical output shapes after.
"""

import asyncio
import json
import pytest
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

from maestro.agents.mock import MockAgent
from maestro.orchestrator import run_orchestration_async, run_orchestration_stream


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agents():
    return [
        MockAgent(name="SnapA", response_style="analytical"),
        MockAgent(name="SnapB", response_style="empathic"),
        MockAgent(name="SnapC", response_style="historical"),
    ]


PROMPT = "What is the meaning of consciousness?"


# ---------------------------------------------------------------------------
# Snapshot: run_orchestration_async
# ---------------------------------------------------------------------------

class TestRunOrchestrationAsyncSnapshot:
    """Verify the output shape and key invariants of run_orchestration_async."""

    def test_returns_expected_top_level_keys(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=True,
            session_logging=False,
        ))
        expected_keys = {"responses", "named_responses", "agent_errors", "final_output", "session_id"}
        assert set(result.keys()) == expected_keys

    def test_named_responses_match_agents(self):
        agents = _make_agents()
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=agents,
            ncg_enabled=True,
            session_logging=False,
        ))
        assert set(result["named_responses"].keys()) == {a.name for a in agents}

    def test_all_responses_are_strings(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=False,
            session_logging=False,
        ))
        for resp in result["named_responses"].values():
            assert isinstance(resp, str)

    def test_final_output_has_consensus(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=True,
            session_logging=False,
        ))
        final = result["final_output"]
        assert "consensus" in final
        assert "confidence" in final
        assert "agreement_ratio" in final

    def test_r2_present_in_final_output(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=True,
            session_logging=False,
        ))
        r2 = result["final_output"].get("r2")
        assert r2 is not None
        assert "grade" in r2
        assert "confidence_score" in r2
        assert "flags" in r2

    def test_session_id_none_when_logging_disabled(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=True,
            session_logging=False,
        ))
        assert result["session_id"] is None

    def test_agent_errors_empty_with_mock_agents(self):
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=_make_agents(),
            ncg_enabled=True,
            session_logging=False,
        ))
        assert result["agent_errors"] == []

    def test_pipeline_survives_single_agent_failure(self):
        """A failing agent should not abort the pipeline."""
        agents = _make_agents()

        class FailAgent:
            name = "FailBot"
            model = "fail"
            async def fetch(self, prompt):
                raise RuntimeError("boom")

        agents.append(FailAgent())
        result = asyncio.run(run_orchestration_async(
            prompt=PROMPT,
            agents=agents,
            ncg_enabled=False,
            session_logging=False,
        ))
        # Pipeline completed despite failure
        assert "FailBot" in result["named_responses"]
        assert len(result["agent_errors"]) >= 1
        # Other agents still produced results
        assert "SnapA" in result["named_responses"]


# ---------------------------------------------------------------------------
# Snapshot: run_orchestration_stream
# ---------------------------------------------------------------------------

class TestRunOrchestrationStreamSnapshot:
    """Verify the SSE event sequence and shapes from run_orchestration_stream."""

    def _collect_events(self, prompt=PROMPT, agents=None, ncg_enabled=True):
        """Run the stream generator and collect all events."""
        agents = agents or _make_agents()

        async def _gather():
            events = []
            async for chunk in run_orchestration_stream(
                prompt=prompt,
                agents=agents,
                ncg_enabled=ncg_enabled,
                session_logging=False,
            ):
                events.append(chunk)
            return events

        return asyncio.run(_gather())

    def _parse_events(self, raw_events):
        """Parse SSE text into (event_type, data) tuples."""
        parsed = []
        for chunk in raw_events:
            lines = chunk.strip().split("\n")
            event_type = None
            data_str = None
            for line in lines:
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_str = line[6:]
            if event_type and data_str:
                parsed.append((event_type, json.loads(data_str)))
        return parsed

    def test_stream_emits_expected_event_types(self):
        raw = self._collect_events()
        parsed = self._parse_events(raw)
        event_types = [e[0] for e in parsed]
        # Must contain these events in order
        assert "stage" in event_types
        assert "agents_done" in event_types
        assert "dissent" in event_types
        assert "consensus" in event_types
        assert "r2" in event_types
        assert "done" in event_types

    def test_stream_agent_response_events(self):
        agents = _make_agents()
        raw = self._collect_events(agents=agents)
        parsed = self._parse_events(raw)
        agent_events = [e for e in parsed if e[0] == "agent_response"]
        assert len(agent_events) == len(agents)
        agent_names = {e[1]["agent"] for e in agent_events}
        assert agent_names == {a.name for a in agents}

    def test_stream_done_event_has_complete_shape(self):
        raw = self._collect_events()
        parsed = self._parse_events(raw)
        done_events = [e for e in parsed if e[0] == "done"]
        assert len(done_events) == 1
        data = done_events[0][1]
        assert "responses" in data
        assert "consensus" in data
        assert "dissent" in data
        assert "r2" in data

    def test_stream_ncg_event_when_enabled(self):
        raw = self._collect_events(ncg_enabled=True)
        parsed = self._parse_events(raw)
        ncg_events = [e for e in parsed if e[0] == "ncg"]
        assert len(ncg_events) == 1
        data = ncg_events[0][1]
        assert "mean_drift" in data
        assert "silent_collapse" in data

    def test_stream_no_ncg_event_when_disabled(self):
        raw = self._collect_events(ncg_enabled=False)
        parsed = self._parse_events(raw)
        ncg_events = [e for e in parsed if e[0] == "ncg"]
        assert len(ncg_events) == 0

    def test_stream_survives_agent_failure(self):
        class FailAgent:
            name = "StreamFail"
            model = "fail"
            async def fetch(self, prompt):
                raise RuntimeError("kaboom")

        agents = _make_agents() + [FailAgent()]
        raw = self._collect_events(agents=agents)
        parsed = self._parse_events(raw)
        event_types = [e[0] for e in parsed]
        assert "done" in event_types  # pipeline completed
