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
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Input, Static, Label, RichLog, Switch, RadioButton, RadioSet

from maestro.tui.backend import MaestroBackend, TUIEvent, create_backend
from maestro.tui.widgets import (
    AgentPanel,
    ClusterDashboard,
    ConsensusPanel,
    ResponseViewer,
    ShardDiscoveryPanel,
    ShardNetworkPanel,
    StatusBar,
)
from maestro.dependency_resolver import resolve_all, DependencyReport, Severity
from maestro.updater import check_for_updates, apply_update, get_auto_updater, UpdateEvent


# ───────────────────────────────────────────────────────────────────
# Prompt templates — persistent storage
# ───────────────────────────────────────────────────────────────────

_TEMPLATES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "prompt_templates.json"

_BUILTIN_TEMPLATES = [
    {"name": "General Question", "prompt": "What is the main ingredient in Coca-Cola?"},
    {"name": "Code Review", "prompt": "Review this code for bugs, security issues, and performance problems:"},
    {"name": "Summarize", "prompt": "Summarize the following text in 3 bullet points:"},
    {"name": "Compare & Contrast", "prompt": "Compare and contrast the following two approaches:"},
    {"name": "Explain Like I'm 5", "prompt": "Explain this concept in simple terms a child could understand:"},
]


def _load_templates() -> list[dict]:
    """Load user templates from disk, falling back to builtins."""
    try:
        if _TEMPLATES_PATH.exists():
            data = json.loads(_TEMPLATES_PATH.read_text())
            if isinstance(data, list) and data:
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return list(_BUILTIN_TEMPLATES)


def _save_templates(templates: list[dict]) -> None:
    """Persist user templates to disk."""
    _TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TEMPLATES_PATH.write_text(json.dumps(templates, indent=2))


def _save_template(name: str, prompt: str) -> None:
    """Append a new template and persist."""
    templates = _load_templates()
    # Avoid duplicates by name
    templates = [t for t in templates if t.get("name") != name]
    templates.insert(0, {"name": name, "prompt": prompt})
    _save_templates(templates)


# ───────────────────────────────────────────────────────────────────
# Prompt result dataclass
# ───────────────────────────────────────────────────────────────────

@dataclass
class PromptResult:
    """Return value from the PromptScreen."""
    prompt: str
    deliberation_enabled: bool = True
    deliberation_rounds: int = 1


# ───────────────────────────────────────────────────────────────────
# Prompt screen (P key) — dedicated full-screen prompt interface
# ───────────────────────────────────────────────────────────────────

class PromptScreen(ModalScreen[PromptResult | None]):
    """Full-screen modal for composing prompts with history, templates,
    and deliberation controls.

    Layout fills available space with a responsive two-column design.
    Deliberation controls are real focusable widgets — use Tab to
    navigate between input, toggle, and round selector; Space/Enter
    to interact.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
        Binding("ctrl+s", "save_template", "Save Template", show=False),
        Binding("ctrl+t", "toggle_deliberation", "Toggle Deliberation", show=False, priority=True),
        Binding("ctrl+r", "cycle_rounds", "Cycle Rounds", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    PromptScreen {
        align: center middle;
    }
    #prompt-dialog {
        width: 90%;
        max-width: 100;
        height: auto;
        max-height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #prompt-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #prompt-text-input {
        width: 100%;
        margin-bottom: 1;
    }
    #prompt-panels {
        height: auto;
        max-height: 12;
    }
    #prompt-history-panel {
        width: 1fr;
        height: auto;
        max-height: 12;
        border: solid $primary;
        padding: 0 1;
        margin-right: 1;
    }
    #prompt-templates-panel {
        width: 1fr;
        height: auto;
        max-height: 12;
        border: solid $primary;
        padding: 0 1;
    }
    .prompt-panel-title {
        text-style: bold;
        color: $primary;
    }
    #prompt-delib-row {
        height: auto;
        margin-top: 1;
        align-vertical: middle;
    }
    #delib-label {
        width: auto;
        padding: 0 1;
    }
    #delib-switch {
        width: auto;
        background: transparent;
    }
    #delib-switch .switch--slider {
        color: $text-muted;
    }
    #delib-switch.-on .switch--slider {
        color: $success;
    }
    #rounds-label {
        width: auto;
        padding: 0 1 0 2;
    }
    #prompt-rounds-selector {
        width: auto;
        height: auto;
        layout: horizontal;
        padding: 0 1;
    }
    #prompt-rounds-selector RadioButton {
        width: auto;
        height: 1;
        padding: 0 1;
        min-width: 5;
        background: transparent;
        color: $text-muted;
    }
    #prompt-rounds-selector RadioButton.-on {
        color: $accent;
        text-style: bold;
    }
    /* Hide the default radio button indicator (the colored block) */
    #prompt-rounds-selector .toggle--button {
        display: none;
    }
    #prompt-hint-row {
        height: 1;
        margin-top: 1;
    }
    #prompt-hints-display {
        width: 100%;
        height: 1;
    }
    """

    def __init__(
        self,
        sessions: list[dict] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._sessions = sessions or []
        self._templates = _load_templates()
        self._deliberation_enabled = True
        self._deliberation_rounds = 1
        self._selected_history_idx: int = -1
        self._selected_template_idx: int = -1

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Label("[bold]  Maestro Prompt[/]", id="prompt-title")
            yield Input(
                placeholder="Type your prompt and press Enter...",
                id="prompt-text-input",
            )
            with Horizontal(id="prompt-panels"):
                with Vertical(id="prompt-history-panel"):
                    yield Label(" │ History", classes="prompt-panel-title")
                    yield Static(
                        self._render_history(), id="prompt-history-list"
                    )
                with Vertical(id="prompt-templates-panel"):
                    yield Label(" │ Templates", classes="prompt-panel-title")
                    yield Static(
                        self._render_templates(), id="prompt-templates-list"
                    )
            with Horizontal(id="prompt-delib-row"):
                yield Label("Deliberation", id="delib-label")
                yield Switch(value=True, id="delib-switch")
                yield Label("Rounds", id="rounds-label")
                yield RadioSet(
                    RadioButton("1", value=True),
                    RadioButton("2"),
                    RadioButton("3"),
                    RadioButton("4"),
                    RadioButton("5"),
                    id="prompt-rounds-selector",
                )
            with Horizontal(id="prompt-hint-row"):
                yield Static(
                    " [dim]Enter[/]:Submit  [dim]Esc[/]:Cancel  "
                    "[dim]Tab[/]:Navigate  "
                    "[dim]Ctrl+S[/]:Save  "
                    "[dim]1-9[/]:History  [dim]F1-F5[/]:Template  "
                    "[dim]Ctrl+T[/]:Delib  [dim]Ctrl+R[/]:Rounds",
                    id="prompt-hints-display",
                )

    def on_mount(self) -> None:
        self.query_one("#prompt-text-input", Input).focus()

    # ── Rendering ─────────────────────────────────────────────────

    def _render_history(self) -> str:
        if not self._sessions:
            return " [dim]No sessions yet[/]"
        lines = []
        for i, s in enumerate(self._sessions[:9]):
            sid = s.get("session_id", "?")[:8]
            grade = s.get("r2_grade", s.get("grade", ""))
            grade_str = f" [{self._grade_color(grade)}]{grade}[/]" if grade else ""
            # Truncate prompt to fit in panel without wrapping
            prompt_text = s.get("prompt", "?")[:30]
            num = i + 1
            marker = "[bold cyan]▸[/]" if i == self._selected_history_idx else " "
            lines.append(f"{marker}[dim]{num}[/] {sid} {prompt_text}{grade_str}")
        return "\n".join(lines)

    def _render_templates(self) -> str:
        if not self._templates:
            return " [dim]No templates[/]"
        lines = []
        for i, t in enumerate(self._templates[:5]):
            name = t.get("name", "?")[:32]
            fkey = f"F{i + 1}"
            marker = "[bold cyan]▸[/]" if i == self._selected_template_idx else " "
            lines.append(f"{marker}[dim]{fkey}[/] {name}")
        return "\n".join(lines)

    @staticmethod
    def _grade_color(grade: str) -> str:
        grade_l = (grade or "").lower()
        if grade_l in ("strong",):
            return "bold green"
        if grade_l in ("acceptable",):
            return "green"
        if grade_l in ("weak",):
            return "yellow"
        if grade_l in ("suspicious",):
            return "bold red"
        return "dim"

    # ── Display updates ───────────────────────────────────────────

    def _update_history_display(self) -> None:
        try:
            self.query_one("#prompt-history-list", Static).update(
                self._render_history()
            )
        except Exception:
            pass

    def _update_templates_display(self) -> None:
        try:
            self.query_one("#prompt-templates-list", Static).update(
                self._render_templates()
            )
        except Exception:
            pass

    # ── Widget event handlers ─────────────────────────────────────

    @on(Switch.Changed, "#delib-switch")
    def _on_delib_switch(self, event: Switch.Changed) -> None:
        self._deliberation_enabled = event.value

    @on(RadioSet.Changed, "#prompt-rounds-selector")
    def _on_rounds_changed(self, event: RadioSet.Changed) -> None:
        self._deliberation_rounds = event.index + 1

    # ── Key handlers ──────────────────────────────────────────────

    @on(Input.Submitted, "#prompt-text-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.dismiss(PromptResult(
            prompt=text,
            deliberation_enabled=self._deliberation_enabled,
            deliberation_rounds=self._deliberation_rounds,
        ))

    def on_key(self, event) -> None:
        key = event.key
        inp = self.query_one("#prompt-text-input", Input)

        # 1-9 — select history item and fill prompt
        # When the input is focused, the digit gets typed first; detect
        # that the value is *only* that digit (user intended to pick
        # history, not type a number in a prompt).
        if key in "123456789":
            cur = inp.value
            just_typed = cur == key  # input was empty, digit just landed
            has_content = bool(cur) and not just_typed
            if has_content:
                return  # Don't hijack when user is composing a real prompt
            idx = int(key) - 1
            if idx < len(self._sessions):
                prompt_text = self._sessions[idx].get("prompt", "")
                if prompt_text:
                    self._selected_history_idx = idx
                    self._selected_template_idx = -1
                    inp.value = prompt_text
                    inp.focus()
                    self._update_history_display()
                    self._update_templates_display()
            return

        # F1-F5 — select template and fill prompt
        fkey_map = {"f1": 0, "f2": 1, "f3": 2, "f4": 3, "f5": 4}
        if key in fkey_map:
            idx = fkey_map[key]
            if idx < len(self._templates):
                prompt_text = self._templates[idx].get("prompt", "")
                if prompt_text:
                    self._selected_template_idx = idx
                    self._selected_history_idx = -1
                    inp.value = prompt_text
                    inp.focus()
                    self._update_history_display()
                    self._update_templates_display()
                    event.prevent_default()
            return

    def action_toggle_deliberation(self) -> None:
        """Toggle deliberation on/off (Ctrl+T — works from any focus)."""
        switch = self.query_one("#delib-switch", Switch)
        switch.toggle()

    def action_cycle_rounds(self) -> None:
        """Cycle deliberation rounds 1→2→...→5→1 (Ctrl+R — works from any focus)."""
        radio_set = self.query_one("#prompt-rounds-selector", RadioSet)
        next_idx = (self._deliberation_rounds % 5)
        # Press the next radio button
        buttons = list(radio_set.query(RadioButton))
        if next_idx < len(buttons):
            buttons[next_idx].value = True

    def action_save_template(self) -> None:
        """Save the current prompt text as a template."""
        inp = self.query_one("#prompt-text-input", Input)
        text = inp.value.strip()
        if not text:
            return
        # Use first 30 chars as the template name
        name = text[:30].rstrip()
        if len(text) > 30:
            name += "..."
        _save_template(name, text)
        self._templates = _load_templates()
        self._update_templates_display()


# ───────────────────────────────────────────────────────────────────
# Session Browser screen (H key) — view full session & deliberation
# ───────────────────────────────────────────────────────────────────

class SessionBrowserScreen(ModalScreen[str | None]):
    """Full-screen modal for browsing session history.

    Lists recent sessions; selecting one shows the full detail including
    agent responses, consensus, deliberation rounds, and metrics.
    Returned value is the session_id if the user wants to re-run the prompt,
    or None if they just close the browser.
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back / Close", priority=True),
        Binding("r", "rerun", "Re-run prompt", show=False),
    ]

    DEFAULT_CSS = """
    SessionBrowserScreen {
        align: center middle;
    }
    #session-browser-dialog {
        width: 96%;
        max-width: 110;
        height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #session-browser-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #session-list-panel {
        height: auto;
        max-height: 12;
        border: solid $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    #session-detail-panel {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #session-detail-log {
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    #session-browser-hints {
        height: 1;
        margin-top: 1;
    }
    .session-panel-title {
        text-style: bold;
        color: $primary;
    }
    """

    def __init__(
        self,
        sessions: list[dict] | None = None,
        backend: MaestroBackend | None = None,
        preselect_index: int = -1,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._sessions = sessions or []
        self._backend = backend
        self._selected_idx = preselect_index
        self._detail_loaded = False
        self._current_session_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="session-browser-dialog"):
            yield Label("[bold]  Session History[/]", id="session-browser-title")
            with Vertical(id="session-list-panel"):
                yield Label(" | Sessions", classes="session-panel-title")
                yield Static(self._render_session_list(), id="session-list-content")
            with VerticalScroll(id="session-detail-panel"):
                yield Label(" | Detail", classes="session-panel-title")
                yield RichLog(
                    highlight=True, markup=True, wrap=True,
                    id="session-detail-log",
                )
            with Horizontal(id="session-browser-hints"):
                yield Static(
                    " [dim]1-9[/]:Select session  "
                    "[dim]R[/]:Re-run prompt  "
                    "[dim]Esc[/]:Back / Close",
                )

    def on_mount(self) -> None:
        if self._selected_idx >= 0 and self._selected_idx < len(self._sessions):
            self._load_detail(self._selected_idx)

    def _render_session_list(self) -> str:
        if not self._sessions:
            return " [dim]No sessions recorded yet[/]"
        lines = []
        for i, s in enumerate(self._sessions[:9]):
            sid = s.get("session_id", "?")[:8]
            ts = s.get("timestamp", "")[:19]
            prompt_text = s.get("prompt", "?")[:40]
            agent_count = s.get("agent_count", "?")
            ncg = s.get("ncg_enabled", False)
            collapse = s.get("silent_collapse", False)
            num = i + 1
            marker = "[bold cyan]>[/]" if i == self._selected_idx else " "
            ncg_str = ""
            if ncg:
                ncg_str = " [green]ncg[/]"
            if collapse:
                ncg_str = " [bold red]COLLAPSE[/]"
            lines.append(
                f"{marker}[dim]{num}[/] {sid} [dim]{ts}[/] "
                f"{prompt_text} [dim]({agent_count} agents{ncg_str})[/]"
            )
        return "\n".join(lines)

    def _update_list_display(self) -> None:
        try:
            self.query_one("#session-list-content", Static).update(
                self._render_session_list()
            )
        except Exception:
            pass

    def _load_detail(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._sessions):
            return
        self._selected_idx = idx
        self._update_list_display()
        session_id = self._sessions[idx].get("session_id", "")
        if session_id and self._backend:
            self._current_session_id = session_id
            self._fetch_detail(session_id)

    @work(thread=False)
    async def _fetch_detail(self, session_id: str) -> None:
        log = self.query_one("#session-detail-log", RichLog)
        log.clear()
        log.write("[bold yellow]Loading session...[/]")
        try:
            detail = await self._backend.get_session_detail(session_id)
            log.clear()
            self._render_detail(detail, log)
            self._detail_loaded = True
        except FileNotFoundError:
            log.clear()
            log.write("[red]Session file not found.[/]")
        except Exception as exc:
            log.clear()
            log.write(f"[red]Error loading session: {exc}[/]")

    def _render_detail(self, detail: dict, log: RichLog) -> None:
        # Header
        sid = detail.get("session_id", "?")
        ts = detail.get("timestamp", "?")
        prompt = detail.get("prompt", "?")
        agents_used = detail.get("agents_used", [])

        log.write(f"[bold cyan]Session:[/] {sid}")
        log.write(f"[bold cyan]Time:[/]    {ts}")
        log.write(f"[bold cyan]Prompt:[/]  {prompt}")
        log.write(f"[bold cyan]Agents:[/]  {', '.join(agents_used)}")
        log.write("")

        # Agent responses
        responses = detail.get("agent_responses", {})
        if responses:
            log.write("[bold magenta]== Agent Responses ==[/]")
            for agent_name, response_text in responses.items():
                log.write(f"\n[bold green][{agent_name}][/]")
                log.write(str(response_text))
            log.write("")

        # Consensus
        consensus = detail.get("consensus", {})
        if isinstance(consensus, dict):
            consensus_text = consensus.get("consensus", "")
            agreement = consensus.get("agreement_ratio")
            quorum = consensus.get("quorum_met")
            confidence = consensus.get("confidence", "")

            if consensus_text or agreement is not None:
                log.write("[bold magenta]== Consensus ==[/]")
                if consensus_text:
                    log.write(str(consensus_text))
                if agreement is not None:
                    pct = f"{agreement:.0%}"
                    style = "green" if agreement >= 0.66 else "yellow" if agreement >= 0.5 else "red"
                    q_str = "[green]MET[/]" if quorum else "[red]NOT MET[/]"
                    log.write(
                        f"  Agreement: [{style}]{pct}[/]  "
                        f"Quorum: {q_str}  Confidence: {confidence}"
                    )
                log.write("")

            # Dissent
            dissent = consensus.get("dissent", {})
            if dissent:
                level = dissent.get("dissent_level", "?")
                internal = dissent.get("internal_agreement")
                outliers = dissent.get("outlier_agents", [])
                style_map = {"low": "green", "moderate": "yellow", "high": "red"}
                style = style_map.get(level, "dim")
                log.write("[bold magenta]== Dissent ==[/]")
                log.write(f"  Level: [{style}]{level}[/]")
                if internal is not None:
                    log.write(f"  Internal agreement: {internal:.2f}")
                if outliers:
                    log.write(f"  Outliers: {', '.join(outliers)}")
                log.write("")

            # R2
            r2 = consensus.get("r2", {})
            if r2:
                grade = r2.get("grade", "?")
                score = r2.get("confidence_score")
                flags = r2.get("flags", [])
                grade_styles = {
                    "strong": "bold green", "acceptable": "green",
                    "weak": "yellow", "suspicious": "bold red",
                }
                g_style = grade_styles.get(grade, "dim")
                log.write("[bold magenta]== R2 Grade ==[/]")
                log.write(f"  Grade: [{g_style}]{(grade or '?').upper()}[/]")
                if score is not None:
                    log.write(f"  Confidence: {score:.2f}")
                if flags:
                    log.write(f"  Flags: {', '.join(flags)}")
                log.write("")

            # Deliberation (from consensus metadata)
            delib = consensus.get("deliberation", {})
            if delib:
                self._render_deliberation_section(delib, log)

        # NCG benchmark
        ncg = detail.get("ncg_benchmark", {})
        if ncg:
            drift = ncg.get("mean_drift")
            collapse = ncg.get("silent_collapse", False)
            ncg_model = ncg.get("ncg_model", "?")
            log.write("[bold magenta]== NCG Benchmark ==[/]")
            log.write(f"  Model: {ncg_model}")
            if drift is not None:
                d_style = "red" if collapse else ("yellow" if drift > 0.5 else "green")
                log.write(f"  Mean drift: [{d_style}]{drift:.3f}[/]")
            if collapse:
                log.write("  [bold red]SILENT COLLAPSE DETECTED[/]")
            log.write("")

        # Metadata
        metadata = detail.get("metadata", {})
        if metadata:
            log.write("[bold magenta]== Metadata ==[/]")
            for k, v in metadata.items():
                log.write(f"  {k}: {v}")
            log.write("")

    def _render_deliberation_section(self, delib: dict, log: RichLog) -> None:
        rounds_req = delib.get("rounds_requested", 0)
        rounds_done = delib.get("rounds_completed", 0)
        skipped = delib.get("skipped", False)
        skip_reason = delib.get("skip_reason", "")
        participants = delib.get("agents_participated", [])
        history = delib.get("history", [])

        log.write("[bold magenta]== Deliberation ==[/]")
        if skipped:
            log.write(f"  [dim]Skipped: {skip_reason}[/]")
            log.write("")
            return

        log.write(
            f"  Rounds: {rounds_done}/{rounds_req}  "
            f"Participants: {', '.join(participants) if participants else '?'}"
        )

        # Show each round's responses
        for rnd in history:
            rnum = rnd.get("round_number", "?")
            responses = rnd.get("responses", {})
            label = "Initial" if rnum == 0 else f"Round {rnum}"
            log.write(f"\n  [bold cyan]--- {label} ---[/]")
            for agent_name, text in responses.items():
                log.write(f"  [bold green][{agent_name}][/]")
                # Truncate very long responses in round view
                display_text = str(text)
                if len(display_text) > 500:
                    display_text = display_text[:500] + "..."
                log.write(f"  {display_text}")
        log.write("")

    def on_key(self, event) -> None:
        key = event.key
        if key in "123456789":
            idx = int(key) - 1
            if idx < len(self._sessions):
                self._load_detail(idx)
            return

    def action_go_back(self) -> None:
        """Go back to list or close."""
        self.dismiss(None)

    def action_rerun(self) -> None:
        """Dismiss with the current session's prompt for re-run."""
        if self._selected_idx >= 0 and self._selected_idx < len(self._sessions):
            sid = self._sessions[self._selected_idx].get("session_id", "")
            self.dismiss(sid)
        else:
            self.dismiss(None)


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
                "  [b]M[/]           Manage instances (spawn / stop)\n"
                "  [b]+[/]           Quick-spawn a new cluster shard\n"
                "  [b]C[/]           Refresh cluster dashboard now\n"
                "  [b]N[/]           Shard network / node details\n"
                "  [b]D[/]           Dependency health check\n"
                "  [b]H[/]           Session history browser\n"
                "  [b]I[/]           Run self-improvement cycle\n"
                "  [b]U[/]           Check for updates\n"
                "  [b]L[/]           Clear response log\n"
                "  [b]Q[/] / [b]Ctrl+C[/]  Quit\n"
            )
            yield Static(
                "[bold]Prompt Screen[/]  (press [b]P[/] to open)\n"
                "  Full-screen prompt interface with history, templates,\n"
                "  and deliberation controls. Type prompt → [b]Enter[/] to submit.\n"
                "  [b]1-9[/]: Re-run from history  [b]F1-F5[/]: Load template\n"
                "  [b]Tab[/]: Navigate controls  [b]Space[/]: Toggle/select\n"
                "  [b]Ctrl+T[/]: Toggle deliberation  [b]Ctrl+R[/]: Cycle rounds\n"
                "  [b]Ctrl+S[/]: Save template\n"
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
            "\n  [bold green]ok Setup complete![/]\n\n"
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
                f"  [red]x Error saving key: {exc}[/]"
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
                    f"  [bold green]ok {label} key is valid![/]"
                )
            elif key_status.valid is False:
                self.app.call_from_thread(
                    status_widget.update,
                    f"  [yellow]!! Key saved but validation failed: "
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
                    f"  [green]ok[/] All clear — "
                    f"{self._report.ok_count} passed, "
                    f"{len(self._report.warnings)} warning(s)"
                )
            else:
                yield Static(
                    f"  [red]x[/] Issues found — "
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
            self._set_status(f"  [red]x {error}[/]")
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
                f"  [green]ok Up to date[/] on [bold]{branch}[/]\n"
                f"  Commit: [dim]{local}[/]"
            )
            self._set_commits("")

    @work(thread=True)
    def action_check(self) -> None:
        self.app.call_from_thread(self._set_status, "  [bold yellow]\u25d4[/] Checking for updates...")
        self.app.call_from_thread(self._set_commits, "")
        try:
            info = check_for_updates()
            self._info = info
            self.app.call_from_thread(self._render_info, info)
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status,
                f"  [red]x Check failed: {exc}[/]",
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
                    f"  [bold green]ok {message}[/]\n\n"
                    f"  Update applied. Restarting in 3 seconds...",
                )
                import time as _time
                _time.sleep(3)
                self.app.call_from_thread(self.app.exit, 42)
            else:
                self.app.call_from_thread(
                    self._set_status,
                    f"  [red]x {message}[/]",
                )
        except Exception as exc:
            self.app.call_from_thread(
                self._set_status,
                f"  [red]x Update failed: {exc}[/]",
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
# Instance manager screen (M key)
# ───────────────────────────────────────────────────────────────────

class InstanceScreen(ModalScreen[None]):
    """Modal overlay for managing Maestro shard/node cluster instances.

    Shows running instances with their cluster role, shard index,
    human-readable name, and IP.  Lets users spawn or stop shard
    members without ever touching the command line.
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("plus", "spawn", "Spawn"),
        ("equal", "spawn", "Spawn"),
        ("shift+equal", "spawn", "Spawn"),
        ("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    InstanceScreen {
        align: center middle;
    }
    #instance-dialog {
        width: 80;
        height: auto;
        max-height: 28;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._instance_data: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="instance-dialog"):
            yield Label("[bold]Maestro Cluster Instances[/]", id="instance-title")
            yield Static("", id="instance-table")
            yield Static("", id="instance-status")
            yield Static(
                "\n[dim]  [b]+[/] Spawn new shard  "
                "[b]1-9[/] Stop instance #N  "
                "[b]R[/] Refresh  "
                "[b]Esc[/] Close[/]",
                id="instance-actions",
            )

    def on_mount(self) -> None:
        self.action_refresh()

    @work(thread=True)
    def action_refresh(self) -> None:
        self._set_status_threadsafe("  [yellow]\u25d4 Scanning cluster...[/]")
        try:
            from maestro.instances import get_all_status
            self._instance_data = get_all_status()
            self.app.call_from_thread(self._render_table)
            self._set_status_threadsafe("")
        except Exception as exc:
            self._set_status_threadsafe(f"  [red]x {exc}[/]")

    def _set_status_threadsafe(self, text: str) -> None:
        """Update the status label from any thread."""
        try:
            self.app.call_from_thread(self._do_set_status, text)
        except Exception:
            # Fallback for cases where app isn't available yet
            try:
                self.query_one("#instance-status", Static).update(text)
            except Exception:
                pass

    def _do_set_status(self, text: str) -> None:
        try:
            self.query_one("#instance-status", Static).update(text)
        except Exception:
            pass

    def _render_table(self) -> None:
        if not self._instance_data:
            self.query_one("#instance-table", Static).update(
                "\n  [dim]No running instances.[/]\n"
                "  Press [b]+[/] to spawn the first shard.\n"
            )
            return

        header = (
            f"\n  {'#':<4} {'Name':<16} {'Role':<13} "
            f"{'Port':<7} {'IP':<16} {'Health'}"
        )
        sep = (
            f"  {'─' * 4} {'─' * 16} {'─' * 13} "
            f"{'─' * 7} {'─' * 16} {'─' * 10}"
        )
        lines = [header, sep]
        for inst in self._instance_data:
            if inst.healthy is True:
                health_str = "[green]\u25cf healthy[/]"
            elif inst.healthy is False:
                health_str = "[red]\u25cf down[/]"
            else:
                health_str = "[yellow]\u25cb checking...[/]"
            name = inst.human_name or inst.project
            role_str = inst.role
            if inst.role == "shard" and inst.shard_index is not None:
                role_str = f"shard [{inst.shard_index}]"
            ip_str = inst.container_ip or "[dim]pending[/]"
            lines.append(
                f"  {inst.number:<4} {name:<16} {role_str:<13} "
                f"{inst.port:<7} {ip_str:<16} {health_str}"
            )

        # Cluster summary
        total = len(self._instance_data)
        healthy = sum(1 for i in self._instance_data if i.healthy)
        shards = sum(1 for i in self._instance_data if i.role == "shard")
        lines.append("")
        lines.append(
            f"  [dim]Cluster: {total} node(s), {shards} shard(s), "
            f"{healthy}/{total} healthy[/]"
        )
        lines.append("")
        self.query_one("#instance-table", Static).update("\n".join(lines))

    @work(thread=True)
    def action_spawn(self) -> None:
        self._set_status_threadsafe(
            "  [bold yellow]\u25d4 Spawning new cluster member...[/]"
        )
        try:
            from maestro.instances import spawn

            def _cb(msg):
                self._set_status_threadsafe(f"  [yellow]\u25d4 {msg}[/]")

            info = spawn(callback=_cb)
            health = "[green]healthy[/]" if info.healthy else "[yellow]starting[/]"
            role_label = info.role
            if info.role == "shard" and info.shard_index is not None:
                role_label = f"shard [{info.shard_index}]"
            self._set_status_threadsafe(
                f"  [bold green]ok[/] [{info.human_name}] spawned as "
                f"[bold]{role_label}[/] on "
                f"[bold]:{info.port}[/] ({health})"
            )
            # Refresh the table and the main dashboard
            from maestro.instances import get_all_status
            self._instance_data = get_all_status()
            self.app.call_from_thread(self._render_table)
            self._refresh_main_dashboard()
        except Exception as exc:
            self._set_status_threadsafe(f"  [red]x Spawn failed: {exc}[/]")

    def _stop_instance(self, n: int) -> None:
        """Stop instance *n* in a background thread."""
        self._do_stop(n)

    @work(thread=True)
    def _do_stop(self, n: int) -> None:
        # Find the human name for the status message
        name = f"maestro-{n}"
        for inst in self._instance_data:
            if inst.number == n and inst.human_name:
                name = inst.human_name
                break
        self._set_status_threadsafe(f"  [yellow]\u25d4 Stopping [{name}]...[/]")
        try:
            from maestro.instances import stop as stop_instance
            stop_instance(n)
            self._set_status_threadsafe(
                f"  [green]ok [{name}] stopped[/]"
            )
            from maestro.instances import get_all_status
            self._instance_data = get_all_status()
            self.app.call_from_thread(self._render_table)
            self._refresh_main_dashboard()
        except Exception as exc:
            self._set_status_threadsafe(f"  [red]x Stop failed: {exc}[/]")

    def _refresh_main_dashboard(self) -> None:
        """Push updated instance data to the main screen's ClusterDashboard."""
        try:
            dashboard = self.app.query_one("#cluster-dashboard", ClusterDashboard)
            self.app.call_from_thread(
                dashboard.update_instances, self._instance_data
            )
        except Exception as exc:
            import logging
            logging.getLogger("maestro.tui").debug(
                "Could not update main dashboard: %s", exc
            )

    def on_key(self, event) -> None:
        """Handle number keys 1-9 to stop, and + to spawn."""
        if event.character == "+":
            # Explicit fallback for terminals where 'plus' binding doesn't fire
            self.action_spawn()
            event.prevent_default()
            return
        if event.character and event.character.isdigit():
            n = int(event.character)
            if n > 0 and any(
                inst.number == n for inst in self._instance_data
            ):
                self._stop_instance(n)
                event.prevent_default()


# ───────────────────────────────────────────────────────────────────
# Main application
# ───────────────────────────────────────────────────────────────────

class MaestroTUI(App):
    """Maestro Orchestrator TUI — mainframe-style dashboard.

    Most actions are bound to a single key.  Press ``?`` for the full
    reference.  Press ``S`` on first run to configure API keys.
    """

    TITLE = "Maestro: Orchestrating Persistent AI Infrastructure"
    SUB_TITLE = "v7.3.0  |  TUI Dashboard"

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
        Binding("m", "show_instances", "Instances", show=False, priority=True),
        Binding("c", "refresh_cluster", "Cluster", show=False, priority=True),
        Binding("i", "run_improve", "Improve", show=False, priority=True),
        Binding("u", "show_update", "Update", show=False, priority=True),
        Binding("l", "clear_log", "Clear", show=False, priority=True),
        Binding("p", "focus_prompt", "Prompt", show=False, priority=True),
        Binding("q", "quit", "Quit", show=False, priority=True),
        # Quick-spawn from main screen (no priority — modal bindings take precedence)
        Binding("plus", "quick_spawn", "Spawn", show=False),
        Binding("equal", "quick_spawn", "Spawn", show=False),
        Binding("shift+equal", "quick_spawn", "Spawn", show=False),
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
        yield ClusterDashboard(id="cluster-dashboard")
        yield ShardDiscoveryPanel(id="discovery-panel")
        yield ShardNetworkPanel(id="shard-panel")
        yield Static(
            " [b]P[/]:Prompt  [b]H[/]:History  [b]?[/]:Help  "
            "[b]Q[/]:Quit",
            id="prompt-hint",
        )
        yield StatusBar()

    def on_mount(self) -> None:
        # Load .env synchronously BEFORE any workers start so that all
        # subsequent os.environ reads (dep-check, first-run, etc.) see keys.
        from maestro.tui.backend import _load_env
        _load_env()

        # Don't auto-focus the prompt — let single-key navigation work
        self._refresh_nodes()
        self._startup_dep_check()
        self._startup_update_check()
        self._start_discovery()
        self._check_first_run()
        self._start_cluster_refresh()

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

    # ── Prompt result handling ─────────────────────────────────────

    def _on_prompt_result(self, result: PromptResult | None) -> None:
        """Callback from PromptScreen — start orchestration if prompt given."""
        if result is None:
            return
        self._run_orchestration(
            result.prompt,
            deliberation_enabled=result.deliberation_enabled,
            deliberation_rounds=result.deliberation_rounds,
        )

    # ── Orchestration ───────────────────────────────────────────────

    @work(thread=False)
    async def _run_orchestration(
        self,
        prompt: str,
        deliberation_enabled: bool = True,
        deliberation_rounds: int = 1,
    ) -> None:
        self._busy = True

        agent_panel = self.query_one("#agent-panel", AgentPanel)
        consensus_panel = self.query_one("#consensus-panel", ConsensusPanel)
        viewer = self.query_one("#response-viewer", ResponseViewer)
        shard_panel = self.query_one("#shard-panel", ShardNetworkPanel)
        status_bar = self.query_one(StatusBar)

        # Reset UI
        agent_panel.set_all_running()
        consensus_panel.reset()
        delib_info = ""
        if deliberation_enabled and deliberation_rounds > 1:
            delib_info = f"  [dim](deliberation: {deliberation_rounds} rounds)[/]"
        elif not deliberation_enabled:
            delib_info = "  [dim](deliberation: off)[/]"
        viewer.write_stage(
            f"Orchestrating: {prompt[:60]}{'...' if len(prompt) > 60 else ''}"
            f"{delib_info}"
        )
        status_bar.set_stage("Querying agents...")

        try:
            async for event in self._backend.orchestrate(
                prompt,
                deliberation_enabled=deliberation_enabled,
                deliberation_rounds=deliberation_rounds,
            ):
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

    @work(thread=False)
    async def action_focus_prompt(self) -> None:
        """Open the dedicated Prompt screen."""
        if self._busy:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info("Pipeline is already running. Please wait...")
            return
        # Fetch session history for the prompt screen
        try:
            sessions = await self._backend.get_session_history(limit=10)
        except Exception:
            sessions = []
        self.push_screen(
            PromptScreen(sessions=sessions),
            callback=self._on_prompt_result,
        )

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

    def action_show_instances(self) -> None:
        self.push_screen(InstanceScreen())

    @work(thread=False)
    async def action_refresh_cluster(self) -> None:
        """Manually refresh the cluster dashboard."""
        await self._refresh_cluster_dashboard()

    @work(thread=True)
    def action_quick_spawn(self) -> None:
        """Spawn a new cluster instance directly from the main screen."""
        import logging
        log = logging.getLogger("maestro.tui")
        try:
            dashboard = self.query_one("#cluster-dashboard", ClusterDashboard)
            self.call_from_thread(
                dashboard.update_status_hint,
                "[bold yellow]\u25d4 Spawning new cluster member...[/]",
            )

            from maestro.instances import spawn, get_all_status
            info = spawn()

            role_label = info.role
            if info.role == "shard" and info.shard_index is not None:
                role_label = f"shard [{info.shard_index}]"
            health = "[green]healthy[/]" if info.healthy else "[yellow]starting[/]"

            instances = get_all_status()
            self.call_from_thread(dashboard.update_instances, instances)
            self.call_from_thread(
                dashboard.update_status_hint,
                f"[bold green]ok[/] [{info.human_name}] spawned as "
                f"[bold]{role_label}[/] on :{info.port} ({health})",
            )
        except Exception as exc:
            log.debug("Quick spawn failed: %s", exc)
            try:
                self.call_from_thread(
                    dashboard.update_status_hint,
                    f"[red]x Spawn failed: {exc}[/]",
                )
            except Exception:
                pass

    def action_show_update(self) -> None:
        self.push_screen(UpdateScreen())

    @work(thread=True)
    def action_run_improve(self) -> None:
        """Run a self-improvement cycle and display results."""
        viewer = self.query_one("#response-viewer", ResponseViewer)
        viewer.write_stage("Self-Improvement Cycle")
        viewer.write_info("  Running MAGI analysis + R2 signal collection...")
        try:
            from maestro.self_improve import SelfImprovementEngine
            engine = SelfImprovementEngine()
            cycle = engine.run_cycle()

            viewer.write_info(f"  Cycle ID: {cycle.cycle_id}")
            viewer.write_info(f"  Sessions analyzed: {cycle.sessions_analyzed}")

            # MAGI report
            if cycle.magi_report:
                magi = cycle.magi_report
                patterns = getattr(magi, "patterns", [])
                viewer.write_info(
                    f"  MAGI patterns: {len(patterns)}"
                )

            # Proposals
            proposals = cycle.proposals or []
            viewer.write_info(f"  Proposals generated: {len(proposals)}")
            for p in proposals[:5]:
                target = getattr(p, "target", "?")
                desc = getattr(p, "description", "?")[:60]
                viewer.write_info(f"    - {target}: {desc}")

            # VIR validation
            if cycle.vir_report:
                vir = cycle.vir_report
                passed = getattr(vir, "passed", None)
                if passed is True:
                    viewer.write_info("  VIR validation: [green]PASSED[/]")
                elif passed is False:
                    viewer.write_info("  VIR validation: [red]FAILED[/]")
                else:
                    viewer.write_info("  VIR validation: [dim]skipped[/]")

            status = cycle.status or "complete"
            viewer.write_info(f"  Status: {status}")
            viewer.write_stage("Self-Improvement Complete")
        except Exception as exc:
            viewer.write_error(f"Self-improvement failed: {exc}")

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
            warnings = report.warnings
            viewer = self.query_one("#response-viewer", ResponseViewer)
            total = len(errors) + len(warnings)
            viewer.write_info(
                f"[yellow]!! {total} issue(s)[/] found  "
                f"([red]{len(errors)} error(s)[/], "
                f"[yellow]{len(warnings)} warning(s)[/])  \u2014  "
                f"Press [b]D[/] for full report."
            )

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
                    f"[bold green]ok {msg}[/] — Restart the TUI to load changes."
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
        try:
            sessions = await self._backend.get_session_history(limit=20)
        except Exception:
            sessions = []
        if not sessions:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_info("No sessions recorded yet.")
            return
        self.push_screen(
            SessionBrowserScreen(
                sessions=sessions,
                backend=self._backend,
            ),
            callback=self._on_session_browser_result,
        )

    def _on_session_browser_result(self, session_id: str | None) -> None:
        """Callback from SessionBrowserScreen — re-run a prompt if requested."""
        if not session_id:
            return
        self._rerun_from_session(session_id)

    @work(thread=False)
    async def _rerun_from_session(self, session_id: str) -> None:
        """Load a session and re-run its prompt via the PromptScreen."""
        try:
            detail = await self._backend.get_session_detail(session_id)
            prompt = detail.get("prompt", "")
            if prompt:
                sessions = await self._backend.get_session_history(limit=10)
                screen = PromptScreen(sessions=sessions)
                # Pre-fill the prompt after mount
                def _prefill(result: PromptResult | None) -> None:
                    self._on_prompt_result(result)
                self.push_screen(screen, callback=_prefill)
                # Set the input value after screen is composed
                await asyncio.sleep(0.1)
                try:
                    inp = screen.query_one("#prompt-text-input", Input)
                    inp.value = prompt
                except Exception:
                    pass
        except Exception as exc:
            viewer = self.query_one("#response-viewer", ResponseViewer)
            viewer.write_error(f"Could not load session: {exc}")

    # ── Cluster dashboard refresh ─────────────────────────────────

    @work(thread=False)
    async def _start_cluster_refresh(self) -> None:
        """Periodically refresh the cluster dashboard with live instance status."""
        import logging
        log = logging.getLogger("maestro.tui")
        while True:
            try:
                await self._refresh_cluster_dashboard()
            except Exception as exc:
                log.debug("Cluster dashboard refresh failed: %s", exc)
            await asyncio.sleep(5.0)

    async def _refresh_cluster_dashboard(self) -> None:
        """Fetch cluster instance status and update the dashboard widget."""
        instances = await asyncio.get_running_loop().run_in_executor(
            None, self._fetch_instances
        )

        dashboard = self.query_one("#cluster-dashboard", ClusterDashboard)
        dashboard.update_instances(instances)

    @staticmethod
    def _fetch_instances() -> list:
        """Synchronous helper to fetch cluster instance status."""
        try:
            from maestro.instances import get_all_status
            return get_all_status()
        except Exception as exc:
            import logging
            logging.getLogger("maestro.tui").debug(
                "Failed to fetch instances: %s", exc
            )
            return []

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
