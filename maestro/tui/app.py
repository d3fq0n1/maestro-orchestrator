"""
Maestro TUI — Main Textual application.

A full orchestration dashboard for SoC devices (Raspberry Pi 5+).
Targets 80x24 minimum terminal size with responsive scaling.

Supports two backend modes:
  - Direct import (in-process): ``python -m maestro.tui``
  - HTTP client: ``python -m maestro.tui --mode http --url http://host:8000``
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Input, Static, Label, RichLog

from maestro.tui.backend import MaestroBackend, TUIEvent, create_backend
from maestro.tui.widgets import (
    AgentPanel,
    ConsensusPanel,
    ResponseViewer,
    ShardNetworkPanel,
    StatusBar,
)


# ───────────────────────────────────────────────────────────────────
# Help screen (F1)
# ───────────────────────────────────────────────────────────────────

class HelpScreen(ModalScreen[None]):
    """Modal overlay showing keybindings and command reference."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 64;
        height: auto;
        max-height: 22;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold]Maestro TUI — Help[/]")
            yield Static("")
            yield Static(
                "[bold]Keybindings[/]\n"
                "  [b]Enter[/]      Submit prompt\n"
                "  [b]F1[/]         This help screen\n"
                "  [b]F2[/]         Refresh shard network nodes\n"
                "  [b]F3[/]         Show API key status\n"
                "  [b]F5[/]         Run self-improvement cycle\n"
                "  [b]Ctrl+L[/]     Clear response log\n"
                "  [b]F10 / Ctrl+C[/]  Quit\n"
            )
            yield Static(
                "[bold]Prompt Commands[/]\n"
                "  [b]/nodes[/]     List storage nodes\n"
                "  [b]/keys[/]      Show API key status\n"
                "  [b]/history[/]   Recent session history\n"
                "  [b]/clear[/]     Clear response log\n"
                "  [b]/quit[/]      Exit the TUI\n"
            )
            yield Static("[dim]Press Escape to close[/]")


# ───────────────────────────────────────────────────────────────────
# Node detail screen (F2)
# ───────────────────────────────────────────────────────────────────

class NodeDetailScreen(ModalScreen[None]):
    """Modal overlay showing detailed storage node information."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    NodeDetailScreen {
        align: center middle;
    }
    #node-dialog {
        width: 72;
        height: auto;
        max-height: 20;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, nodes: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._nodes = nodes

    def compose(self) -> ComposeResult:
        with Vertical(id="node-dialog"):
            yield Label("[bold]Shard Network — Node Details[/]")
            yield Static("")
            if not self._nodes:
                yield Static("  No storage nodes registered.")
            else:
                for n in self._nodes[:10]:
                    nid = n.get("node_id", "?")
                    host = n.get("host", "?")
                    port = n.get("port", "?")
                    status = n.get("status", "?")
                    rep = n.get("reputation_score", 0.0)
                    latency = n.get("mean_latency_ms", 0.0)
                    mem_total = n.get("total_memory_mb", 0)
                    mem_used = n.get("used_memory_mb", 0)
                    shards = n.get("shards", [])

                    status_style = {
                        "available": "green", "busy": "yellow",
                        "probation": "red", "offline": "dim",
                    }.get(status, "dim")

                    yield Static(
                        f" [{status_style}]\u25cf[/] [bold]{nid}[/]  "
                        f"{host}:{port}  [{status_style}]{status}[/]\n"
                        f"   rep: {rep:.2f}  latency: {latency:.1f}ms  "
                        f"mem: {mem_used}/{mem_total}MB  shards: {len(shards)}"
                    )
            yield Static("")
            yield Static("[dim]Press Escape to close[/]")


# ───────────────────────────────────────────────────────────────────
# Key status screen (F3)
# ───────────────────────────────────────────────────────────────────

class KeyStatusScreen(ModalScreen[None]):
    """Modal overlay showing API key configuration status."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    KeyStatusScreen {
        align: center middle;
    }
    #key-dialog {
        width: 60;
        height: auto;
        max-height: 16;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, keys: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._keys = keys

    def compose(self) -> ComposeResult:
        with Vertical(id="key-dialog"):
            yield Label("[bold]API Key Status[/]")
            yield Static("")
            if not self._keys:
                yield Static("  Unable to retrieve key status.")
            else:
                for k in self._keys:
                    label = k.get("label", "?")
                    configured = k.get("configured", False)
                    masked = k.get("masked", "---")
                    if configured:
                        yield Static(f"  [green]\u25cf[/] {label:<16} {masked}")
                    else:
                        yield Static(f"  [red]\u25cb[/] {label:<16} [dim]not configured[/]")
            yield Static("")
            yield Static("[dim]Press Escape to close[/]")


# ───────────────────────────────────────────────────────────────────
# Main application
# ───────────────────────────────────────────────────────────────────

class MaestroTUI(App):
    """Maestro Orchestrator TUI — full dashboard for SoC devices."""

    TITLE = "Maestro Orchestrator"
    SUB_TITLE = "Raspberry Pi 5 TUI"

    CSS_PATH = "maestro_tui.tcss"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("f1", "show_help", "Help", show=False),
        Binding("f2", "show_nodes", "Nodes", show=False),
        Binding("f3", "show_keys", "Keys", show=False),
        Binding("f5", "run_improve", "Improve", show=False),
        Binding("ctrl+l", "clear_log", "Clear", show=False),
        Binding("f10", "quit", "Quit", show=False),
    ]

    def __init__(self, backend: MaestroBackend, **kwargs):
        super().__init__(**kwargs)
        self._backend = backend
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-row"):
            yield AgentPanel(id="agent-panel")
            yield ConsensusPanel(id="consensus-panel")
        yield ResponseViewer(id="response-viewer")
        yield ShardNetworkPanel(id="shard-panel")
        yield Input(placeholder="Enter prompt (or /help for commands)...", id="prompt-input")
        yield StatusBar()

    def on_mount(self) -> None:
        self.query_one("#prompt-input", Input).focus()
        self._refresh_nodes()

    # ── Input handling ──────────────────────────────────────────────

    @on(Input.Submitted, "#prompt-input")
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""
        lower = text.lower()

        # Handle commands
        if lower in ("/quit", "/exit", "/q"):
            self.exit()
            return
        if lower in ("/help", "/h"):
            self.action_show_help()
            return
        if lower in ("/clear", "/cls"):
            self.action_clear_log()
            return
        if lower in ("/nodes",):
            self.action_show_nodes()
            return
        if lower in ("/keys",):
            self.action_show_keys()
            return
        if lower in ("/history",):
            self._show_history()
            return

        if self._busy:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info("Pipeline is already running. Please wait...")
            return

        self._run_orchestration(text)

    # ── Orchestration ───────────────────────────────────────────────

    @work(thread=False)
    async def _run_orchestration(self, prompt: str) -> None:
        self._busy = True

        agent_panel = self.query_one("#agent-panel", AgentPanel)
        consensus_panel = self.query_one("#consensus-panel", ConsensusPanel)
        viewer = self.query_one("#response-viewer", ResponseViewer)
        shard_panel = self.query_one("#shard-panel", ShardNetworkPanel)
        status_bar = self.query_one(StatusBar)

        # Reset UI
        agent_panel.set_all_running()
        consensus_panel.reset()
        viewer.write_stage(f"Orchestrating: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
        status_bar.set_stage("Querying agents...")

        try:
            async for event in self._backend.orchestrate(prompt):
                self._handle_event(event)
        except Exception as exc:
            viewer.write_error(f"{type(exc).__name__}: {exc}")
        finally:
            self._busy = False
            status_bar.reset()

    def _handle_event(self, event: TUIEvent) -> None:
        agent_panel = self.query_one("#agent-panel", AgentPanel)
        consensus_panel = self.query_one("#consensus-panel", ConsensusPanel)
        viewer = self.query_one("#response-viewer", ResponseViewer)
        status_bar = self.query_one(StatusBar)

        if event.kind == "stage":
            msg = event.data.get("message", event.data.get("name", ""))
            status_bar.set_stage(msg)
            viewer.write_stage(msg)

        elif event.kind == "agent_response":
            agent = event.data.get("agent", "?")
            text = event.data.get("text", "")
            is_error = event.data.get("is_error", False)
            agent_panel.set_agent_status(agent, "error" if is_error else "done")
            viewer.write_agent(agent, text, is_error=is_error)
            done_count = event.data.get("agents_done", 0)
            total = event.data.get("agents_total", 0)
            if total:
                status_bar.set_stage(f"Agents: {done_count}/{total}")

        elif event.kind == "agents_done":
            pass  # All agents have been handled individually

        elif event.kind == "dissent":
            consensus_panel.update_dissent(event.data)

        elif event.kind == "ncg":
            consensus_panel.update_ncg(event.data)

        elif event.kind == "consensus":
            consensus_panel.update_consensus(event.data)
            consensus_text = event.data.get("consensus", "")
            if consensus_text:
                viewer.write_consensus(consensus_text)

        elif event.kind == "r2":
            consensus_panel.update_r2(event.data)

        elif event.kind == "done":
            session_id = event.data.get("session_id", "")
            if session_id:
                viewer.write_info(f"Session: {session_id}")
            viewer.write_stage("Done")

        elif event.kind == "error":
            viewer.write_error(event.data.get("error", "Unknown error"))

    # ── Actions / keybindings ───────────────────────────────────────

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    @work(thread=False)
    async def action_show_nodes(self) -> None:
        try:
            nodes = await self._backend.list_nodes()
        except Exception:
            nodes = []
        self.push_screen(NodeDetailScreen(nodes))
        shard_panel = self.query_one("#shard-panel", ShardNetworkPanel)
        shard_panel.update_nodes(nodes)

    @work(thread=False)
    async def action_show_keys(self) -> None:
        try:
            keys = await self._backend.list_keys()
        except Exception:
            keys = []
        self.push_screen(KeyStatusScreen(keys))

    def action_run_improve(self) -> None:
        viewer = self.query_one("#response-viewer", ResponseViewer)
        viewer.write_info(
            "Self-improvement via TUI is planned for a future release. "
            "Use the CLI (/improve) or the Web UI for now."
        )

    def action_clear_log(self) -> None:
        viewer = self.query_one("#response-viewer", ResponseViewer)
        viewer.clear_log()

    # ── Background helpers ──────────────────────────────────────────

    @work(thread=False)
    async def _refresh_nodes(self) -> None:
        try:
            nodes = await self._backend.list_nodes()
            shard_panel = self.query_one("#shard-panel", ShardNetworkPanel)
            shard_panel.update_nodes(nodes)
        except Exception:
            pass

    @work(thread=False)
    async def _show_history(self) -> None:
        viewer = self.query_one("#response-viewer", ResponseViewer)
        try:
            sessions = await self._backend.get_session_history(limit=10)
            if not sessions:
                viewer.write_info("No sessions recorded yet.")
                return
            viewer.write_stage("Recent Sessions")
            for s in sessions:
                sid = s.get("session_id", "?")[:12]
                prompt_text = s.get("prompt", "?")[:50]
                grade = s.get("r2_grade", s.get("grade", "?"))
                viewer.write_info(f"  {sid}  {grade:<12} {prompt_text}")
        except Exception as exc:
            viewer.write_error(f"Could not load history: {exc}")
