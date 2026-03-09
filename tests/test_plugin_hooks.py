"""
Tests for plugin hook firing order, context passing, and orchestrator integration.
"""

import asyncio
import json

import pytest

from maestro.plugins.manager import ModManager, HOOK_POINTS
from maestro.agents.mock import MockAgent
from maestro.orchestrator import run_orchestration_async, run_orchestration_stream


class TestHookFiringOrder:
    def test_hooks_fire_in_registration_order(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))
        order = []

        mgr.register_hook("pre_orchestration", lambda ctx: order.append(1) or ctx)
        mgr.register_hook("pre_orchestration", lambda ctx: order.append(2) or ctx)
        mgr.register_hook("pre_orchestration", lambda ctx: order.append(3) or ctx)

        asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "test"}))
        assert order == [1, 2, 3]

    def test_hook_can_transform_prompt(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))

        def transform(ctx):
            ctx["prompt"] = ctx["prompt"] + " [transformed]"
            return ctx

        mgr.register_hook("pre_orchestration", transform)

        result = asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "hello"}))
        assert result["prompt"] == "hello [transformed]"

    def test_hook_returning_none_skips(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))

        def noop_hook(ctx):
            return None  # returning None means no modification

        mgr.register_hook("pre_orchestration", noop_hook)

        result = asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "hello"}))
        assert result["prompt"] == "hello"

    def test_hook_error_doesnt_crash_pipeline(self, tmp_path):
        mgr = ModManager(plugins_dir=str(tmp_path))

        def bad_hook(ctx):
            raise RuntimeError("hook error")

        mgr.register_hook("pre_orchestration", bad_hook)

        # Should not raise
        result = asyncio.run(mgr.run_hooks("pre_orchestration", {"prompt": "test"}))
        assert result["prompt"] == "test"


class TestOrchestratorWithHooks:
    """Verify hooks fire correctly within the actual orchestration pipeline."""

    def test_async_orchestration_with_mod_manager(self):
        mgr = ModManager()
        hook_log = []

        def pre_hook(ctx):
            hook_log.append("pre_orchestration")
            return ctx

        def post_agg_hook(ctx):
            hook_log.append("post_aggregation")
            return ctx

        def post_r2_hook(ctx):
            hook_log.append("post_r2_scoring")
            return ctx

        mgr.register_hook("pre_orchestration", pre_hook)
        mgr.register_hook("post_aggregation", post_agg_hook)
        mgr.register_hook("post_r2_scoring", post_r2_hook)

        agents = [
            MockAgent(name="HookA", response_style="analytical"),
            MockAgent(name="HookB", response_style="empathic"),
        ]

        result = asyncio.run(run_orchestration_async(
            prompt="test hooks",
            agents=agents,
            ncg_enabled=False,
            session_logging=False,
            mod_manager=mgr,
        ))

        assert "pre_orchestration" in hook_log
        assert "post_aggregation" in hook_log
        assert "post_r2_scoring" in hook_log
        # Pipeline still produces valid output
        assert "final_output" in result
        assert result["final_output"].get("r2") is not None

    def test_stream_orchestration_with_mod_manager(self):
        mgr = ModManager()
        hook_log = []

        mgr.register_hook("pre_orchestration", lambda ctx: hook_log.append("pre") or ctx)
        mgr.register_hook("post_aggregation", lambda ctx: hook_log.append("post_agg") or ctx)

        agents = [
            MockAgent(name="StreamHookA", response_style="analytical"),
        ]

        async def collect():
            events = []
            async for chunk in run_orchestration_stream(
                prompt="stream hook test",
                agents=agents,
                ncg_enabled=False,
                session_logging=False,
                mod_manager=mgr,
            ):
                events.append(chunk)
            return events

        events = asyncio.run(collect())
        assert "pre" in hook_log
        assert "post_agg" in hook_log
        # Stream still completes
        assert any("done" in e for e in events)

    def test_orchestration_works_without_mod_manager(self):
        """Verify the pipeline works identically without mod_manager (backward compat)."""
        agents = [
            MockAgent(name="NoHookA", response_style="analytical"),
            MockAgent(name="NoHookB", response_style="empathic"),
        ]

        result = asyncio.run(run_orchestration_async(
            prompt="no hooks test",
            agents=agents,
            ncg_enabled=True,
            session_logging=False,
            mod_manager=None,
        ))

        assert "final_output" in result
        assert result["final_output"].get("consensus") is not None
