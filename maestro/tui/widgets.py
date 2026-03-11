"""
Custom Textual widgets for the Maestro TUI dashboard.

Designed for 80x24 minimum terminal size on SoC devices (Raspberry Pi 5).
All widgets are lightweight and avoid expensive reflows.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Label, ProgressBar, DataTable, RichLog


# ---------------------------------------------------------------------------
# Agent status indicators
# ---------------------------------------------------------------------------

_STATUS_STYLES = {
    "ready":    ("dim", "idle"),
    "running":  ("bold yellow", "..."),
    "done":     ("bold green", "ok"),
    "error":    ("bold red", "err"),
}


class AgentIndicator(Static):
    """Single-line status indicator for one agent."""

    status = reactive("ready")

    def __init__(self, agent_name: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.update_display()

    def watch_status(self, value: str) -> None:
        self.update_display()

    def update_display(self) -> None:
        style, label = _STATUS_STYLES.get(self.status, ("dim", "?"))
        icon = {"ready": "\u25cb", "running": "\u25d4", "done": "\u25cf", "error": "\u25cf"}.get(
            self.status, "\u25cb"
        )
        self.update(f" [{style}]{icon}[/] {self.agent_name:<10} {label}")


class AgentPanel(Widget):
    """Panel showing all agent statuses."""

    DEFAULT_CSS = """
    AgentPanel {
        height: auto;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, agent_names: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._agent_names = agent_names or ["Sol", "Aria", "Prism", "TempAgent"]
        self._indicators: dict[str, AgentIndicator] = {}

    def compose(self) -> ComposeResult:
        yield Label(" Pipeline", id="agent-panel-title")
        for name in self._agent_names:
            indicator = AgentIndicator(name, id=f"agent-{name}")
            self._indicators[name] = indicator
            yield indicator

    def set_agent_status(self, agent_name: str, status: str) -> None:
        if agent_name in self._indicators:
            self._indicators[agent_name].status = status

    def reset_all(self) -> None:
        for indicator in self._indicators.values():
            indicator.status = "ready"

    def set_all_running(self) -> None:
        for indicator in self._indicators.values():
            indicator.status = "running"


# ---------------------------------------------------------------------------
# Consensus / metrics panel
# ---------------------------------------------------------------------------

class ConsensusPanel(Widget):
    """Panel showing consensus, quorum, R2, and dissent metrics."""

    DEFAULT_CSS = """
    ConsensusPanel {
        height: auto;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(" Consensus", id="consensus-panel-title")
        yield Static(" Agreement : ---", id="metric-agreement")
        yield Static(" Quorum    : ---", id="metric-quorum")
        yield Static(" Confidence: ---", id="metric-confidence")
        yield Static(" Dissent   : ---", id="metric-dissent")
        yield Static(" R2 Grade  : ---", id="metric-r2")
        yield Static(" NCG Drift : ---", id="metric-ncg")

    def update_consensus(self, data: dict) -> None:
        ratio = data.get("agreement_ratio")
        quorum = data.get("quorum_met")
        confidence = data.get("confidence", "---")

        if ratio is not None:
            pct = f"{ratio:.0%}"
            style = "green" if ratio >= 0.66 else "yellow" if ratio >= 0.5 else "red"
            self.query_one("#metric-agreement", Static).update(
                f" Agreement : [{style}]{pct}[/]"
            )
        if quorum is not None:
            q_str = "[green]MET[/]" if quorum else "[red]NOT MET[/]"
            self.query_one("#metric-quorum", Static).update(f" Quorum    : {q_str}")
        self.query_one("#metric-confidence", Static).update(
            f" Confidence: {confidence}"
        )

    def update_dissent(self, data: dict) -> None:
        level = data.get("dissent_level", "---")
        agreement = data.get("internal_agreement")
        style_map = {"low": "green", "moderate": "yellow", "high": "red"}
        style = style_map.get(level, "dim")
        label = f"[{style}]{level}[/]"
        if agreement is not None:
            label += f" ({agreement:.2f})"
        self.query_one("#metric-dissent", Static).update(f" Dissent   : {label}")

    def update_r2(self, data: dict) -> None:
        grade = data.get("grade", "---")
        score = data.get("confidence_score")
        grade_styles = {
            "strong": "bold green",
            "acceptable": "green",
            "weak": "yellow",
            "suspicious": "bold red",
        }
        style = grade_styles.get(grade, "dim")
        label = f"[{style}]{grade.upper()}[/]"
        if score is not None:
            label += f" ({score:.2f})"
        flags = data.get("flags", [])
        if flags:
            label += f"  flags: {len(flags)}"
        self.query_one("#metric-r2", Static).update(f" R2 Grade  : {label}")

    def update_ncg(self, data: dict) -> None:
        drift = data.get("mean_drift")
        collapse = data.get("silent_collapse", False)
        if drift is not None:
            style = "red" if collapse else ("yellow" if drift > 0.5 else "green")
            label = f"[{style}]{drift:.3f}[/]"
            if collapse:
                label += " [bold red]COLLAPSE[/]"
            self.query_one("#metric-ncg", Static).update(f" NCG Drift : {label}")

    def reset(self) -> None:
        for mid in ("agreement", "quorum", "confidence", "dissent", "r2", "ncg"):
            self.query_one(f"#metric-{mid}", Static).update(
                f" {mid.capitalize():<11}: ---"
            )


# ---------------------------------------------------------------------------
# Response viewer
# ---------------------------------------------------------------------------

class ResponseViewer(Widget):
    """Scrollable log showing agent responses and consensus output."""

    DEFAULT_CSS = """
    ResponseViewer {
        height: 1fr;
        border: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="response-log")

    @property
    def log(self) -> RichLog:
        return self.query_one("#response-log", RichLog)

    def write_stage(self, message: str) -> None:
        self.log.write(f"[bold cyan]>> {message}[/]")

    def write_agent(self, agent: str, text: str, is_error: bool = False) -> None:
        style = "red" if is_error else "green"
        self.log.write(f"\n[bold {style}][{agent}][/]")
        self.log.write(text)

    def write_consensus(self, text: str) -> None:
        self.log.write(f"\n[bold magenta]== Consensus ==[/]")
        self.log.write(text)

    def write_info(self, text: str) -> None:
        self.log.write(f"[dim]{text}[/]")

    def write_error(self, text: str) -> None:
        self.log.write(f"[bold red]ERROR: {text}[/]")

    def clear_log(self) -> None:
        self.log.clear()


# ---------------------------------------------------------------------------
# Shard network panel
# ---------------------------------------------------------------------------

class ShardNetworkPanel(Widget):
    """Compact panel showing storage node status."""

    DEFAULT_CSS = """
    ShardNetworkPanel {
        height: auto;
        max-height: 8;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(" Shard Network", id="shard-panel-title")
        yield Static(" No nodes registered", id="shard-node-list")

    def update_nodes(self, nodes: list[dict]) -> None:
        if not nodes:
            self.query_one("#shard-node-list", Static).update(" No nodes registered")
            return

        lines = []
        for n in nodes[:6]:
            node_id = n.get("node_id", "?")[:16]
            status = n.get("status", "?")
            rep = n.get("reputation_score", 0.0)
            shards = n.get("shards", [])
            shard_count = len(shards)

            status_style = {
                "available": "green", "busy": "yellow",
                "probation": "red", "offline": "dim", "evicted": "dim red",
            }.get(status, "dim")

            # Build compact layer range summary
            layer_info = ""
            if shards:
                ranges = []
                for s in shards[:3]:
                    lr = s.get("layer_range", [])
                    if len(lr) >= 2:
                        ranges.append(f"{lr[0]}-{lr[1]}")
                if ranges:
                    layer_info = f"L[{','.join(ranges)}]"

            # Memory bar
            total_mem = n.get("total_memory_mb", 0)
            used_mem = n.get("used_memory_mb", 0)
            mem_str = ""
            if total_mem > 0:
                pct = min(used_mem / total_mem, 1.0)
                filled = int(pct * 8)
                mem_str = f"\u2588" * filled + "\u2591" * (8 - filled)
                mem_str = f" {mem_str} {used_mem}M"

            line = (
                f" [{status_style}]\u25cf[/] {node_id:<16} "
                f"{layer_info:<12} rep:{rep:.2f}{mem_str}"
            )
            lines.append(line)

        if len(nodes) > 6:
            lines.append(f" ... and {len(nodes) - 6} more nodes")

        self.query_one("#shard-node-list", Static).update("\n".join(lines))


# ---------------------------------------------------------------------------
# LAN Discovery panel
# ---------------------------------------------------------------------------

_ADJACENCY_ICONS = {
    "discovered":     ("[yellow]\u25cb[/]",  "discovered"),
    "handshake_sent": ("[yellow]\u25d4[/]",  "handshake..."),
    "handshake_acked":("[yellow]\u25d1[/]",  "ack'd"),
    "confirmed":      ("[green]\u25cf[/]",   "adjacent"),
    "stale":          ("[red]\u25cf[/]",      "offline"),
}


class ShardDiscoveryPanel(Widget):
    """Panel showing LAN shard discovery, adjacencies, and Maestro Node status."""

    DEFAULT_CSS = """
    ShardDiscoveryPanel {
        height: auto;
        max-height: 10;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(" LAN Shards", id="discovery-panel-title")
        yield Static(" [dim]identity[/]: ---", id="discovery-identity")
        yield Static(" [dim]maestro node[/]: ---", id="discovery-node-status")
        yield Static(" [dim]waiting for beacons...[/]", id="discovery-peer-list")

    def update_identity(self, identity: dict) -> None:
        """Update the local shard identity display."""
        name = identity.get("human_name", "?")
        uid_short = identity.get("uid", "?")[:8]
        host = identity.get("host", "?")
        port = identity.get("port", "?")
        self.query_one("#discovery-identity", Static).update(
            f" [bold cyan]\u2726[/] [bold]{name}[/] "
            f"[dim]({uid_short})[/]  {host}:{port}"
        )

    def update_node_status(self, node_status: dict) -> None:
        """Update the Maestro Node formation status."""
        formed = node_status.get("formed", False)
        if formed:
            names = node_status.get("member_names", [])
            label = ", ".join(names[:3])
            self.query_one("#discovery-node-status", Static).update(
                f" [bold green]\u2714 MAESTRO NODE[/]  [{label}]"
            )
        else:
            self.query_one("#discovery-node-status", Static).update(
                f" [dim]\u25cb maestro node: not formed (need 3 shards)[/]"
            )

    def update_peers(self, peers: list[dict]) -> None:
        """Update the peer list with adjacency status lights."""
        if not peers:
            self.query_one("#discovery-peer-list", Static).update(
                " [dim]no neighbors discovered yet[/]"
            )
            return

        lines = []
        for p in peers[:6]:
            adj_state = p.get("adjacency", "discovered")
            icon, adj_label = _ADJACENCY_ICONS.get(
                adj_state, ("[dim]\u25cb[/]", "?")
            )
            name = p.get("name", "?")
            host = p.get("host", "?")
            uid_short = p.get("uid_short", "?")
            latency = p.get("latency_ms", 0)

            alive = p.get("alive", False)
            if not alive and adj_state != "stale":
                icon = "[red]\u25cf[/]"
                adj_label = "offline"

            latency_str = f" {latency:.0f}ms" if latency > 0 else ""
            line = (
                f" {icon} {name:<18} "
                f"[dim]{uid_short}[/]  {host:<15} "
                f"{adj_label}{latency_str}"
            )
            lines.append(line)

        if len(peers) > 6:
            lines.append(f" ... and {len(peers) - 6} more")

        self.query_one("#discovery-peer-list", Static).update("\n".join(lines))

    def update_full(self, snapshot: dict) -> None:
        """Convenience: update all sub-elements from a full discovery snapshot."""
        self.update_identity(snapshot.get("identity", {}))
        self.update_node_status(snapshot.get("node_status", {}))
        # Convert peers dict to list for display
        peers_dict = snapshot.get("peers", {})
        peer_list = []
        for uid, pdata in peers_dict.items():
            peer_list.append({
                "uid_short": uid[:8],
                "name": pdata.get("human_name", "?"),
                "host": pdata.get("host", "?"),
                "adjacency": pdata.get("adjacency", "discovered"),
                "alive": pdata.get("is_alive", False),
                "adjacent": pdata.get("is_adjacent", False),
                "latency_ms": pdata.get("latency_ms", 0),
            })
        self.update_peers(peer_list)


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

class StatusBar(Widget):
    """Bottom status bar with pipeline stage and keybinding hints."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $text;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            " [b]F1[/]:Help  [b]F2[/]:Nodes  [b]F3[/]:Keys  [b]F4[/]:Deps  "
            "[b]F5[/]:Improve  [b]Ctrl+L[/]:Clear  [b]F10[/]:Quit",
            id="status-bar-content",
        )

    def set_stage(self, stage: str) -> None:
        self.query_one("#status-bar-content", Static).update(
            f" [bold yellow]{stage}[/]  |  "
            "[b]F1[/]:Help [b]F2[/]:Nodes [b]F3[/]:Keys [b]F4[/]:Deps [b]F10[/]:Quit"
        )

    def reset(self) -> None:
        self.query_one("#status-bar-content", Static).update(
            " [b]F1[/]:Help  [b]F2[/]:Nodes  [b]F3[/]:Keys  [b]F4[/]:Deps  "
            "[b]F5[/]:Improve  [b]Ctrl+L[/]:Clear  [b]F10[/]:Quit"
        )
