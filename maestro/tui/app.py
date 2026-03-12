"""
Maestro TUI — Main Textual application.

A full orchestration dashboard for SoC devices (Raspberry Pi 5+).
Targets 80x24 minimum terminal size with responsive scaling.

Mainframe-style single-keypress navigation — most actions are bound to
a single key so you never need to type long commands.  Where text input
is required (prompts, API keys) the TUI opens a focused input dialog.

Supports two backend modes:
  - Direct import (in-process): ``python -m maestro.tui``
  - HTTP client: ``python -m maestro.tui --mode http --url http://host:8000``
"""

from __future__ import annotations

import asyncio
import os
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
    ShardDiscoveryPanel,
    ShardNetworkPanel,
    StatusBar,
)
from maestro.dependency_resolver import resolve_all, DependencyReport, Severity
from maestro.updater import check_for_updates, apply_update, get_auto_updater, UpdateEvent


# ───────────────────────────────────────────────────────────────────
# Help screen (? key)
# ───────────────────────────────────────────────────────────────────

class HelpScreen(ModalScreen[None]):
    """Modal overlay showing single-key actions and command reference."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 68;
        height: auto;
        max-height: 24;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold]Maestro TUI — Quick Reference[/]")
            yield Static("")
            yield Static(
                "[bold]Single-Key Actions[/]  (press anywhere except the prompt)\n"
                "  [b]?[/]           This help screen\n"
                "  [b]S[/]           API key setup wizard\n"
                "  [b]K[/]           Show API key status\n"
                "  [b]N[/]           Shard network / node details\n"
                "  [b]D[/]           Dependency health check\n"
                "  [b]H[/]           Recent session history\n"
                "  [b]I[/]           Self-improvement (planned)\n"
                "  [b]U[/]           Check for updates\n"
                "  [b]L[/]           Clear response log\n"
                "  [b]Q[/] / [b]Ctrl+C[/]  Quit\n"
            )
            yield Static(
                "[bold]Prompt Input[/]  (press [b]Enter[/] or [b]P[/] to focus)\n"
                "  Type your prompt, then [b]Enter[/] to submit.\n"
                "  Slash commands also work: /nodes /keys /history /clear /quit\n"
            )
            yield Static(
                "[bold]Tips[/]\n"
                "  First time?  Press [b]S[/] to configure API keys.\n"
                "  Paste keys from clipboard into the setup wizard.\n"
                "  You can also load keys from a .env file."
            )
            yield Static("")
            yield Static("[dim]Press Escape to close[/]")


# ───────────────────────────────────────────────────────────────────
# API Key Setup Wizard (S key)
# ───────────────────────────────────────────────────────────────────

def _info_label(provider: str) -> str:
    """Get display label for a provider."""
    from maestro.keyring import PROVIDERS
    return PROVIDERS.get(provider, {}).get("label", provider)


class KeySetupWizard(ModalScreen[None]):
    """Guided API key configuration wizard.

    Walks through each provider, lets the user paste or type their key,
    validates it, and persists to .env.  Designed for first-run but can
    be opened any time via the S key.
    """

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    KeySetupWizard {
        align: center middle;
    }
    #setup-dialog {
        width: 74;
        height: auto;
        max-height: 26;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #setup-input {
        margin: 1 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from maestro.keyring import PROVIDERS
        self._providers = list(PROVIDERS.items())
        self._current = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-dialog"):
            yield Label("[bold]API Key Setup[/]", id="setup-title")
            yield Static("", id="setup-provider-info")
            yield Input(
                placeholder="Paste your API key here...",
                password=True,
                id="setup-input",
            )
            yield Static("", id="setup-status")
            yield Static("", id="setup-nav")
            yield Static(
                "[dim]\n"
                "  Tips for entering API keys:\n"
                "  \u2022 Copy the key from your provider's dashboard\n"
                "  \u2022 Right-click or Ctrl+Shift+V to paste in most terminals\n"
                "  \u2022 Keys starting with 'sk-' (OpenAI), 'sk-ant-' (Anthropic),\n"
                "    'AI' (Google), or 'sk-or-' (OpenRouter)\n"
                "  \u2022 Keys are saved to .env and never leave your machine\n"
                "  \u2022 Press Enter to save, Tab to skip, Escape to close[/]",
                id="setup-tips",
            )

    def on_mount(self) -> None:
        self._show_current_provider()
        self.query_one("#setup-input", Input).focus()

    def _show_current_provider(self) -> None:
        if self._current >= len(self._providers):
            self._show_complete()
            return

        provider, info = self._providers[self._current]
        label = info["label"]
        env_var = info["env_var"]
        prefix = info.get("prefix", "")
        signup_url = info.get("signup_url", "")
        num = self._current + 1
        total = len(self._providers)

        # Check if already configured
        from maestro.keyring import get_key, mask_key
        existing = get_key(provider)
        existing_hint = ""
        if existing:
            existing_hint = f"\n  [green]\u25cf Already configured:[/] {mask_key(existing)}"

        self.query_one("#setup-provider-info", Static).update(
            f"\n  [bold]({num}/{total}) {label}[/]  "
            f"env: [cyan]{env_var}[/]  prefix: [cyan]{prefix}[/]\n"
            f"  Get your key: [underline]{signup_url}[/]"
            f"{existing_hint}"
        )
        self.query_one("#setup-status", Static).update("")
        self.query_one("#setup-nav", Static).update(
            f"  [b]Enter[/]: Save key  |  [b]Tab[/]: Skip  |  "
            f"[b]Escape[/]: Close  |  ({num}/{total})"
        )

        inp = self.query_one("#setup-input", Input)
        inp.value = ""
        inp.display = True
        inp.focus()

    def _show_complete(self) -> None:
        self.query_one("#setup-provider-info", Static).update(
            "\n  [bold green]\u2714 Setup complete![/]\n\n"
            "  All providers have been reviewed.\n"
            "  Press [b]K[/] any time to check key status.\n"
            "  Press [b]S[/] any time to re-run this wizard."
        )
        self.query_one("#setup-input", Input).display = False
        self.query_one("#setup-status", Static).update("")
        self.query_one("#setup-nav", Static).update(
            "  Press [b]Escape[/] to close."
        )
        self.query_one("#setup-tips", Static).display = False

    @on(Input.Submitted, "#setup-input")
    def _on_key_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            # Treat empty Enter like Tab — skip to next
            self._current += 1
            self._show_current_provider()
            return

        if self._current >= len(self._providers):
            return

        provider, info = self._providers[self._current]
        self._save_and_validate(provider, value)

    def key_tab(self) -> None:
        """Skip current provider."""
        self._current += 1
        self._show_current_provider()

    @work(thread=True)
    def _save_and_validate(self, provider: str, value: str) -> None:
        from maestro.keyring import set_key, validate_key
        import asyncio

        status_widget = self.query_one("#setup-status", Static)

        # Save key
        try:
            set_key(provider, value)
            self.app.call_from_thread(
                status_widget.update,
                f"  [yellow]\u25d4 Saved. Validating...[/]"
            )
        except Exception as exc:
            self.app.call_from_thread(
                status_widget.update,
                f"  [red]\u2718 Error saving key: {exc}[/]"
            )
            return

        # Validate
        try:
            loop = asyncio.new_event_loop()
            key_status = loop.run_until_complete(validate_key(provider))
            loop.close()

            label = _info_label(provider)
            if key_status.valid:
                self.app.call_from_thread(
                    status_widget.update,
                    f"  [bold green]\u2714 {label} key is valid![/]"
                )
            elif key_status.valid is False:
                self.app.call_from_thread(
                    status_widget.update,
                    f"  [yellow]\u26a0 Key saved but validation failed: "
                    f"{key_status.error}[/]\n"
                    f"  [dim]The key is saved — you can fix it later.[/]"
                )
            else:
                self.app.call_from_thread(
                    status_widget.update,
                    f"  [dim]Key saved (validation skipped).[/]"
                )
        except Exception:
            self.app.call_from_thread(
                status_widget.update,
                f"  [dim]Key saved (could not validate — network issue?).[/]"
            )

        # Auto-advance after a brief pause
        import time
        time.sleep(1.2)
        self._current += 1
        self.app.call_from_thread(self._show_current_provider)


# ───────────────────────────────────────────────────────────────────
# Node detail screen (N key)
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
        self._node_data = nodes

    def compose(self) -> ComposeResult:
        with Vertical(id="node-dialog"):
            yield Label("[bold]Shard Network — Node Details[/]")
            yield Static("")
            if not self._node_data:
                yield Static("  No storage nodes registered.")
            else:
                for n in self._node_data[:10]:
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
# Key status screen (K key)
# ───────────────────────────────────────────────────────────────────

class KeyStatusScreen(ModalScreen[None]):
    """Modal overlay showing API key configuration status."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("s", "open_setup", "Setup"),
    ]

    DEFAULT_CSS = """
    KeyStatusScreen {
        align: center middle;
    }
    #key-dialog {
        width: 60;
        height: auto;
        max-height: 18;
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
            yield Static("[dim]Press [b]S[/] to run setup wizard  |  Escape to close[/]")

    def action_open_setup(self) -> None:
        self.dismiss()
        self.app.push_screen(KeySetupWizard())


# ───────────────────────────────────────────────────────────────────
# Dependency check screen (D key)
# ───────────────────────────────────────────────────────────────────

class DependencyScreen(ModalScreen[None]):
    """Modal overlay showing dependency and environment health checks."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    DependencyScreen {
        align: center middle;
    }
    #dep-dialog {
        width: 76;
        height: auto;
        max-height: 24;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def __init__(self, report: DependencyReport, **kwargs):
        super().__init__(**kwargs)
        self._report = report

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dep-dialog"):
            yield Label("[bold]Dependency Health Check[/]")
            yield Static("")

            # Summary line
            if self._report.healthy:
                yield Static(
                    f"  [green]\u2714[/] All clear — "
                    f"{self._report.ok_count} passed, "
                    f"{len(self._report.warnings)} warning(s)"
                )
            else:
                yield Static(
                    f"  [red]\u2718[/] Issues found — "
                    f"{len(self._report.errors)} error(s), "
                    f"{len(self._report.warnings)} warning(s), "
                    f"{self._report.ok_count} ok"
                )

            yield Static("")

            # Group by category
            categories = ["runtime", "python", "system", "api_key"]
            cat_labels = {
                "runtime": "Runtime",
                "python": "Python Packages",
                "system": "System Tools",
                "api_key": "API Keys",
            }

            for cat in categories:
                items = [c for c in self._report.checks if c.category == cat]
                if not items:
                    continue
                yield Static(f"  [bold]{cat_labels.get(cat, cat)}[/]")
                for c in items:
                    icon = {
                        Severity.OK: "[green]\u25cf[/]",
                        Severity.WARN: "[yellow]\u25cf[/]",
                        Severity.ERROR: "[red]\u25cf[/]",
                    }.get(c.severity, "[dim]\u25cb[/]")
                    yield Static(f"    {icon} {c.message}")
                    if c.hint:
                        yield Static(f"      [dim]{c.hint}[/]")
                yield Static("")

            yield Static("[dim]Press Escape to close[/]")


# ───────────────────────────────────────────────────────────────────
# Update screen (U key)
# ───────────────────────────────────────────────────────────────────

class UpdateScreen(ModalScreen[str | None]):
    """Modal overlay for checking, applying, and configuring auto-updates."""

    BINDINGS = [
        ("escape", "dismiss(None)", "Close"),
        ("c", "check", "Check"),
        ("a", "apply", "Apply"),
        ("t", "toggle_auto", "Toggle auto"),
    ]

    DEFAULT_CSS = """
    UpdateScreen {
        align: center middle;
    }
    #update-dialog {
        width: 72;
        height: auto;
        max-height: 26;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, update_info: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self._info = update_info

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="update-dialog"):
            yield Label("[bold]Auto-Updater[/]", id="update-title")
            yield Static("", id="update-auto-status")
            yield Static("", id="update-status")
            yield Static("", id="update-commits")
            yield Static("")
            yield Static(
                "[dim]  [b]C[/] Check now  "
                "[b]A[/] Apply update  "
                "[b]T[/] Toggle auto-update  "
                "[b]Esc[/] Close[/]",
                id="update-actions",
            )

    def on_mount(self) -> None:
        self._render_auto_status()
        if self._info:
            self._render_info(self._info)
        else:
            self.action_check()

    def _render_auto_status(self) -> None:
        updater = get_auto_updater()
        status = updater.status()
        enabled = status.get("enabled", False)
        auto_apply = status.get("auto_apply", False)
        interval = status.get("poll_interval", 60)
        applied_count = status.get("updates_applied", 0)

        enabled_str = "[bold green]ON[/]" if enabled else "[dim]OFF[/]"
        apply_str = "[green]auto-apply[/]" if auto_apply else "[dim]notify only[/]"
        applied_str = f"  [dim]({applied_count} applied this session)[/]" if applied_count else ""

        self.query_one("#update-auto-status", Static).update(
            f"  Auto-update: {enabled_str}  |  {apply_str}  |  "
            f"every {interval}s{applied_str}"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#update-status", Static).update(text)

    def _set_commits(self, text: str) -> None:
        self.query_one("#update-commits", Static).update(text)

    def _render_info(self, info: dict) -> None:
        error = info.get("error")
        if error:
            self._set_status(f"  [red]\u2718 {error}[/]")
            self._set_commits("")
            return

        local = info.get("local_commit", "?")
        remote = info.get("remote_commit", "?")
        branch = info.get("branch", "?")
        available = info.get("available", False)

        if available:
            new_commits = info.get("new_commits", [])
            count = len(new_commits)
            self._set_status(
                f"  [bold yellow]\u2191 Update available[/] on [bold]{branch}[/]\n"
                f"  Local: [dim]{local or 'unknown'}[/]  "
                f"Remote: [bold]{remote}[/]  "
                f"({count} new commit{'s' if count != 1 else ''})\n\n"
                f"  Press [b]A[/] to apply the update."
            )
            if new_commits:
                lines = "\n".join(f"    [dim]{c}[/]" for c in new_commits[:10])
                if count > 10:
                    lines += f"\n    [dim]... and {count - 10} more[/]"
                self._set_commits(f"  [bold]New commits:[/]\n{lines}")
            else:
                self._set_commits("")
        else:
            self._set_status(
                f"  [green]\u2714 Up to date[/] on [bold]{branch}[/]\n"
                f"  Commit: [dim]{local}[/]"
            )
            self._set_commits("")

    @work(thread=True)
    def action_check(self) -> None:
        self._set_status("  [bold yellow]\u25d4[/] Checking for updates...")
        self._set_commits("")
        try:
            info = check_for_updates()
            self._info = info
            self.app.call_from_thread(self._render_info, info)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status,
                f"  [red]\u2718 Check failed: {exc}[/]",
            )

    @work(thread=True)
    def action_apply(self) -> None:
        if not self._info or not self._info.get("available"):
            self.app.call_from_thread(
                self._set_status,
                "  [dim]No update available. Press [b]C[/] to check first.[/]",
            )
            return

        self.app.call_from_thread(
            self._set_status,
            "  [bold yellow]\u25d4[/] Applying update...",
        )
        self.app.call_from_thread(self._set_commits, "")
        try:
            result = apply_update()
            success = result.get("success", False)
            message = result.get("message", "")
            if success:
                self.app.call_from_thread(
                    self._set_status,
                    f"  [bold green]\u2714 {message}[/]\n\n"
                    f"  Restart the TUI to load changes.",
                )
            else:
                self.app.call_from_thread(
                    self._set_status,
                    f"  [red]\u2718 {message}[/]",
                )
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status,
                f"  [red]\u2718 Update failed: {exc}[/]",
            )

    def action_toggle_auto(self) -> None:
        """Toggle the auto-updater between enabled/disabled."""
        updater = get_auto_updater()
        new_enabled = not updater.enabled
        updater.configure(enabled=new_enabled)
        # Persist
        os.environ["MAESTRO_AUTO_UPDATE"] = "1" if new_enabled else "0"
        self._render_auto_status()
        viewer = self.app.query_one("#response-viewer", ResponseViewer)
        if new_enabled:
            viewer.write_info(
                f"[bold green]Auto-updater enabled[/] — "
                f"checking every {updater.poll_interval}s"
            )
        else:
            viewer.write_info("[dim]Auto-updater disabled.[/]")


# ───────────────────────────────────────────────────────────────────
# Main application
# ───────────────────────────────────────────────────────────────────

class MaestroTUI(App):
    """Maestro Orchestrator TUI — mainframe-style dashboard.

    Most actions are bound to a single key.  Press ``?`` for the full
    reference.  Press ``S`` on first run to configure API keys.
    """

    TITLE = "Maestro Orchestrator"
    SUB_TITLE = "TUI Dashboard"

    CSS_PATH = "maestro_tui.tcss"

    # ── Single-keypress bindings (mainframe-style) ─────────────────
    #
    # These fire when the prompt input is NOT focused.  When the
    # prompt is focused, regular typing takes priority.
    BINDINGS: ClassVar[list[Binding]] = [
        # Navigation & information
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("s", "show_setup", "Setup", show=False, priority=True),
        Binding("k", "show_keys", "Keys", show=False, priority=True),
        Binding("n", "show_nodes", "Nodes", show=False, priority=True),
        Binding("d", "show_deps", "Deps", show=False, priority=True),
        Binding("h", "show_history_key", "History", show=False, priority=True),
        Binding("i", "run_improve", "Improve", show=False, priority=True),
        Binding("u", "show_update", "Update", show=False, priority=True),
        Binding("l", "clear_log", "Clear", show=False, priority=True),
        Binding("p", "focus_prompt", "Prompt", show=False, priority=True),
        Binding("q", "quit", "Quit", show=False, priority=True),
        # Function keys still work as alternatives
        Binding("f1", "show_help", "Help", show=False),
        Binding("f2", "show_nodes", "Nodes", show=False),
        Binding("f3", "show_keys", "Keys", show=False),
        Binding("f4", "show_deps", "Deps", show=False),
        Binding("f5", "run_improve", "Improve", show=False),
        Binding("f6", "show_update", "Update", show=False),
        Binding("ctrl+l", "clear_log", "Clear", show=False),
        Binding("f10", "quit", "Quit", show=False),
    ]

    def __init__(self, backend: MaestroBackend, **kwargs):
        super().__init__(**kwargs)
        self._backend = backend
        self._busy = False
        self._discovery_engine = None
        self._first_run_checked = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-row"):
            yield AgentPanel(id="agent-panel")
            yield ConsensusPanel(id="consensus-panel")
        yield ResponseViewer(id="response-viewer")
        yield ShardDiscoveryPanel(id="discovery-panel")
        yield ShardNetworkPanel(id="shard-panel")
        yield Input(placeholder="Press P to focus | Enter to submit | ? for help", id="prompt-input")
        yield StatusBar()

    def on_mount(self) -> None:
        # Don't auto-focus the prompt — let single-key navigation work
        self._refresh_nodes()
        self._startup_dep_check()
        self._startup_update_check()
        self._start_discovery()
        self._check_first_run()

    # ── First-run detection ────────────────────────────────────────

    @work(thread=True)
    def _check_first_run(self) -> None:
        """Detect if no API keys are configured and offer the setup wizard."""
        if self._first_run_checked:
            return
        self._first_run_checked = True

        from maestro.keyring import list_keys
        keys = list_keys()
        configured_count = sum(1 for k in keys if k.configured)

        if configured_count == 0:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info(
                "[bold yellow]No API keys configured.[/]\n"
                "  Press [b]S[/] to run the setup wizard and paste your keys.\n"
                "  You need at least one provider key (OpenAI, Anthropic, Google, or OpenRouter)."
            )
            # Auto-open the wizard
            self.app.call_from_thread(self._open_setup_wizard)

    def _open_setup_wizard(self) -> None:
        self.push_screen(KeySetupWizard())

    # ── Input handling ──────────────────────────────────────────────

    @on(Input.Submitted, "#prompt-input")
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""
        lower = text.lower()

        # Handle slash commands (still supported for power users)
        if lower in ("/quit", "/exit", "/q"):
            self.exit()
            return
        if lower in ("/help", "/h", "/?"):
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
        if lower in ("/setup",):
            self.action_show_setup()
            return
        if lower in ("/shards", "/discovery", "/lan"):
            self._show_discovery_status()
            return
        if lower in ("/history",):
            self._show_history()
            return
        if lower in ("/deps", "/dependencies", "/health"):
            self.action_show_deps()
            return
        if lower in ("/update", "/updates"):
            self.action_show_update()
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

    # ── Actions / single-key bindings ──────────────────────────────

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_show_setup(self) -> None:
        self.push_screen(KeySetupWizard())

    def action_focus_prompt(self) -> None:
        self.query_one("#prompt-input", Input).focus()

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

    def action_show_deps(self) -> None:
        report = resolve_all()
        self.push_screen(DependencyScreen(report))

    def action_show_update(self) -> None:
        self.push_screen(UpdateScreen())

    def action_run_improve(self) -> None:
        viewer = self.query_one("#response-viewer", ResponseViewer)
        viewer.write_info(
            "Self-improvement via TUI is planned for a future release. "
            "Use the CLI (/improve) or the Web UI for now."
        )

    def action_clear_log(self) -> None:
        viewer = self.query_one("#response-viewer", ResponseViewer)
        viewer.clear_log()

    def action_show_history_key(self) -> None:
        self._show_history()

    # ── Background helpers ──────────────────────────────────────────

    @work(thread=False)
    async def _refresh_nodes(self) -> None:
        try:
            nodes = await self._backend.list_nodes()
            shard_panel = self.query_one("#shard-panel", ShardNetworkPanel)
            shard_panel.update_nodes(nodes)
        except Exception:
            pass

    @work(thread=True)
    def _startup_dep_check(self) -> None:
        report = resolve_all()
        if not report.healthy:
            errors = report.errors
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_error(
                f"Dependency check: {len(errors)} error(s), "
                f"{len(report.warnings)} warning(s)"
            )
            for c in errors:
                viewer.write_error(f"  {c.message}")
                if c.hint:
                    viewer.write_info(f"    {c.hint}")
            viewer.write_info("  Press [b]D[/] for full report.")

    @work(thread=True)
    def _startup_update_check(self) -> None:
        """Check for updates in the background at startup and start auto-update loop."""
        try:
            info = check_for_updates()
        except Exception:
            info = None

        if info and info.get("available"):
            count = len(info.get("new_commits", []))
            branch = info.get("branch", "?")
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info(
                f"[bold yellow]\u2191 Update available[/] — "
                f"{count} new commit{'s' if count != 1 else ''} on {branch}. "
                f"Press [b]U[/] to review."
            )

        # Start the auto-update background loop
        self.app.call_from_thread(self._start_auto_update_loop)

    @work(thread=False)
    async def _start_auto_update_loop(self) -> None:
        """Run the auto-updater background loop in the TUI."""
        updater = get_auto_updater()

        def _on_event(event: UpdateEvent) -> None:
            """Handle auto-updater events in the TUI."""
            try:
                viewer = self.query_one("#response-viewer", ResponseViewer)
            except Exception:
                return

            if event.kind == "available":
                count = len(event.data.get("new_commits", []))
                branch = event.data.get("branch", "?")
                self.call_from_thread(
                    viewer.write_info,
                    f"[bold yellow]\u2191 Update available[/] — "
                    f"{count} new commit{'s' if count != 1 else ''} on {branch}. "
                    f"Press [b]U[/] to review."
                )
            elif event.kind == "applying":
                self.call_from_thread(
                    viewer.write_info,
                    "[bold yellow]\u25d4 Auto-updating...[/]"
                )
            elif event.kind == "applied":
                msg = event.data.get("message", "Updated successfully")
                self.call_from_thread(
                    viewer.write_info,
                    f"[bold green]\u2714 {msg}[/] — Restart the TUI to load changes."
                )
            elif event.kind == "error":
                error = event.data.get("error", "Unknown error")
                phase = event.data.get("phase", "")
                self.call_from_thread(
                    viewer.write_info,
                    f"[dim]Auto-updater {phase} error: {error}[/]"
                )

        updater.on_event(_on_event)

        # Start the background polling loop
        await updater.start()

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

    # ── LAN Shard Discovery ────────────────────────────────────────

    @work(thread=False)
    async def _show_discovery_status(self) -> None:
        """Show detailed LAN discovery status in the response viewer."""
        viewer = self.query_one("#response-viewer", ResponseViewer)
        if not self._discovery_engine:
            viewer.write_info("LAN discovery is not running.")
            return

        snap = self._discovery_engine.snapshot()
        ident = snap["identity"]
        viewer.write_stage("LAN Shard Discovery")
        viewer.write_info(
            f"  Identity: {ident['human_name']} ({ident['uid'][:8]})"
        )
        viewer.write_info(f"  Host: {ident['host']}:{ident['port']}")
        viewer.write_info(
            f"  Peers: {snap['peer_count']} discovered, "
            f"{snap['alive_count']} alive, "
            f"{snap['adjacent_count']} adjacent"
        )

        node = snap["node_status"]
        if node["formed"]:
            names = ", ".join(node["member_names"])
            viewer.write_info(f"  Maestro Node: FORMED [{names}]")
        else:
            viewer.write_info("  Maestro Node: not formed (need 3 adjacent shards)")

        if snap["peers"]:
            viewer.write_info("")
            for uid, p in snap["peers"].items():
                alive_icon = "[green]OK[/]" if p["is_alive"] else "[red]DOWN[/]"
                adj = p["adjacency"]
                lat = f" {p['latency_ms']:.0f}ms" if p["latency_ms"] else ""
                viewer.write_info(
                    f"  {alive_icon} {p['human_name']:<18} "
                    f"{uid[:8]}  {p['host']:<15} {adj}{lat}"
                )

    @work(thread=False)
    async def _start_discovery(self) -> None:
        """Start the LAN shard discovery engine and refresh loop."""
        try:
            from maestro.lan_discovery import ShardDiscoveryEngine
            self._discovery_engine = ShardDiscoveryEngine()
            await self._discovery_engine.start()
            discovery_panel = self.query_one("#discovery-panel", ShardDiscoveryPanel)
            discovery_panel.update_identity(self._discovery_engine.identity.to_dict())
            discovery_panel.update_node_status(self._discovery_engine.node_status.to_dict())
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info(
                f"LAN discovery started: {self._discovery_engine.identity.human_name} "
                f"({self._discovery_engine.identity.uid[:8]})"
            )
            # Start periodic refresh
            self._refresh_discovery_loop()
        except Exception as exc:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info(f"LAN discovery unavailable: {exc}")

    @work(thread=False)
    async def _refresh_discovery_loop(self) -> None:
        """Periodically update the discovery panel with latest peer state."""
        while self._discovery_engine and self._discovery_engine._running:
            try:
                snapshot = self._discovery_engine.snapshot()
                discovery_panel = self.query_one("#discovery-panel", ShardDiscoveryPanel)
                discovery_panel.update_full(snapshot)
            except Exception:
                pass
            await asyncio.sleep(2.0)
