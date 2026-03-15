"""
Custom Textual widgets for the Maestro TUI dashboard.

Designed for 80x24 minimum terminal size on SoC devices (Raspberry Pi 5).
All widgets are lightweight and avoid expensive reflows.
"""

from __future__ import annotations

import asyncio
import re
import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Label, ProgressBar, DataTable, RichLog


# ---------------------------------------------------------------------------
# Agent status indicators
# ---------------------------------------------------------------------------

def _sanitize_id(name: str) -> str:
    """Convert a display name to a valid Textual widget identifier."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-")


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
        self._agent_names = agent_names or ["GPT-4o", "Claude Sonnet 4.6", "Gemini 2.5 Flash", "Llama 3.3 70B"]
        self._indicators: dict[str, AgentIndicator] = {}

    def compose(self) -> ComposeResult:
        yield Label(" Pipeline", id="agent-panel-title")
        for name in self._agent_names:
            indicator = AgentIndicator(name, id=f"agent-{_sanitize_id(name)}")
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
# BTOP-style shard network monitor
# ---------------------------------------------------------------------------

# Spinner frames for connected shards (bright green asterisk cycle)
_SPINNER_FRAMES = ["\u2736", "\u2737", "\u2738", "\u2739", "\u273a", "\u2739", "\u2738", "\u2737"]
_SPINNER_LEN = len(_SPINNER_FRAMES)


class ShardNetworkPanel(Widget):
    """BTOP-style panel showing storage node status with animated indicators.

    Connected/available nodes show a spinning bright-green asterisk.
    Missing/offline nodes show a static red indicator.
    """

    DEFAULT_CSS = """
    ShardNetworkPanel {
        height: auto;
        max-height: 10;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._storage_nodes: list[dict] = []
        self._frame = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Label(" Shard Network", id="shard-panel-title")
        yield Static(" [dim]No nodes registered[/]", id="shard-node-list")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.25, self._tick)

    def _tick(self) -> None:
        """Advance spinner frame and re-render if nodes exist."""
        if not self._storage_nodes:
            return
        self._frame = (self._frame + 1) % _SPINNER_LEN
        self._render_nodes()

    def update_nodes(self, nodes: list[dict]) -> None:
        self._storage_nodes = nodes
        self._render_nodes()

    def _render_nodes(self) -> None:
        if not self._storage_nodes:
            self.query_one("#shard-node-list", Static).update(
                " [dim]No nodes registered[/]"
            )
            return

        lines = []
        for n in self._storage_nodes[:6]:
            node_id = n.get("node_id", "?")[:16]
            status = n.get("status", "?")
            rep = n.get("reputation_score", 0.0)
            shards = n.get("shards", [])
            shard_count = len(shards)

            # BTOP-style status indicators
            if status in ("available", "busy"):
                # Spinning bright-green asterisk for connected nodes
                spinner = _SPINNER_FRAMES[self._frame]
                if status == "busy":
                    icon = f"[bold yellow]{spinner}[/]"
                else:
                    icon = f"[bold green]{spinner}[/]"
            elif status == "probation":
                icon = "[bold red]\u2718[/]"
            elif status in ("offline", "evicted"):
                icon = "[red]\u25cf[/]"
            else:
                icon = "[dim]\u25cb[/]"

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

            # Memory bar (BTOP-style block meter)
            total_mem = n.get("total_memory_mb", 0)
            used_mem = n.get("used_memory_mb", 0)
            mem_str = ""
            if total_mem > 0:
                pct = min(used_mem / total_mem, 1.0)
                filled = int(pct * 8)
                bar = "\u2588" * filled + "\u2591" * (8 - filled)
                mem_color = "green" if pct < 0.6 else "yellow" if pct < 0.85 else "red"
                mem_str = f" [{mem_color}]{bar}[/] {used_mem}M"

            # Reputation color
            rep_color = "green" if rep >= 0.7 else "yellow" if rep >= 0.4 else "red"

            line = (
                f" {icon} {node_id:<16} "
                f"{layer_info:<12} [{rep_color}]rep:{rep:.2f}[/]{mem_str}"
            )
            lines.append(line)

        if len(self._storage_nodes) > 6:
            lines.append(f" [dim]... and {len(self._storage_nodes) - 6} more nodes[/]")

        self.query_one("#shard-node-list", Static).update("\n".join(lines))


# ---------------------------------------------------------------------------
# LAN Discovery panel (BTOP-style with spinners)
# ---------------------------------------------------------------------------

_ADJACENCY_ICONS = {
    "discovered":     ("[yellow]\u25cb[/]",  "discovered"),
    "handshake_sent": ("[yellow]\u25d4[/]",  "handshake..."),
    "handshake_acked":("[yellow]\u25d1[/]",  "ack'd"),
    "confirmed":      ("[green]\u25cf[/]",   "adjacent"),
    "stale":          ("[red]\u25cf[/]",      "offline"),
}


class ShardDiscoveryPanel(Widget):
    """Panel showing LAN shard discovery, adjacencies, and Maestro Node status.

    Adjacent/confirmed peers show spinning green asterisks.
    Stale/offline peers show static red indicators.
    """

    DEFAULT_CSS = """
    ShardDiscoveryPanel {
        height: auto;
        max-height: 10;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._peers: list[dict] = []
        self._identity: dict = {}
        self._node_status: dict = {}
        self._frame = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Label(" LAN Shards", id="discovery-panel-title")
        yield Static(" [dim]identity[/]: ---", id="discovery-identity")
        yield Static(" [dim]maestro node[/]: ---", id="discovery-node-status")
        yield Static(" [dim]waiting for beacons...[/]", id="discovery-peer-list")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.25, self._tick_peers)

    def _tick_peers(self) -> None:
        if not self._peers:
            return
        self._frame = (self._frame + 1) % _SPINNER_LEN
        self._render_peers()

    def update_identity(self, identity: dict) -> None:
        """Update the local shard identity display."""
        self._identity = identity
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
        self._node_status = node_status
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
        self._peers = peers
        self._render_peers()

    def _render_peers(self) -> None:
        if not self._peers:
            self.query_one("#discovery-peer-list", Static).update(
                " [dim]no neighbors discovered yet[/]"
            )
            return

        lines = []
        for p in self._peers[:6]:
            adj_state = p.get("adjacency", "discovered")
            name = p.get("name", "?")
            host = p.get("host", "?")
            uid_short = p.get("uid_short", "?")
            latency = p.get("latency_ms", 0)
            alive = p.get("alive", False)

            # BTOP-style: spinning green asterisk for live adjacent peers
            if alive and adj_state == "confirmed":
                spinner = _SPINNER_FRAMES[self._frame]
                icon = f"[bold green]{spinner}[/]"
                adj_label = "adjacent"
            elif alive and adj_state in ("handshake_sent", "handshake_acked"):
                spinner = _SPINNER_FRAMES[self._frame]
                icon = f"[bold yellow]{spinner}[/]"
                adj_label = _ADJACENCY_ICONS.get(adj_state, ("[dim]\u25cb[/]", "?"))[1]
            elif not alive or adj_state == "stale":
                icon = "[red]\u25cf[/]"
                adj_label = "offline"
            else:
                icon, adj_label = _ADJACENCY_ICONS.get(
                    adj_state, ("[dim]\u25cb[/]", "?")
                )

            latency_str = f" {latency:.0f}ms" if latency > 0 else ""
            line = (
                f" {icon} {name:<18} "
                f"[dim]{uid_short}[/]  {host:<15} "
                f"{adj_label}{latency_str}"
            )
            lines.append(line)

        if len(self._peers) > 6:
            lines.append(f" [dim]... and {len(self._peers) - 6} more[/]")

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
# Cluster instance dashboard (live monitoring)
# ---------------------------------------------------------------------------

# Health-state icons
_HEALTH_ICONS = {
    True:  ("bold green", "\u25cf"),    # ● green for healthy
    False: ("bold red",   "\u25cf"),    # ● red for down
    None:  ("dim",        "\u25cb"),    # ○ dim for unknown
}


class ClusterDashboard(Widget):
    """Always-visible panel showing live cluster instance health.

    Renders a compact table of running Maestro instances with BTOP-style
    spinning indicators for healthy nodes.  Auto-refreshed by the app
    every few seconds.  When empty, shows a hint to spawn the first
    instance.

    QOL features:
    - Spinning asterisks on healthy nodes (matches ShardNetworkPanel style)
    - Color-coded roles (cyan orchestrator, yellow shard)
    - Uptime display when available
    - Cluster summary line with node/shard/health counts
    - Compact single-line-per-instance layout
    """

    DEFAULT_CSS = """
    ClusterDashboard {
        height: auto;
        max-height: 12;
        min-height: 3;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._instances: list = []
        self._frame = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Label(" Cluster", id="cluster-dash-title")
        yield Static(
            " [dim]No cluster instances. Press [b]M[/b] to manage.[/]",
            id="cluster-dash-content",
        )

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.25, self._tick)

    def _tick(self) -> None:
        if not self._instances:
            return
        self._frame = (self._frame + 1) % _SPINNER_LEN
        self._render()

    def update_instances(self, instances: list) -> None:
        """Update the instance list (expects InstanceInfo objects or dicts)."""
        self._instances = instances
        self._render()

    def _render(self) -> None:
        content = self.query_one("#cluster-dash-content", Static)

        if not self._instances:
            content.update(
                " [dim]No cluster instances. Press [b]M[/b] to manage.[/]"
            )
            return

        lines = []
        # Compact header
        lines.append(
            f" {'#':<3} {'Name':<14} {'Role':<12} "
            f"{'Port':<6} {'IP':<15} {'Health'}"
        )
        lines.append(
            f" {'─' * 3} {'─' * 14} {'─' * 12} "
            f"{'─' * 6} {'─' * 15} {'─' * 8}"
        )

        for inst in self._instances:
            # Support both InstanceInfo objects and dicts
            if hasattr(inst, "healthy"):
                healthy = inst.healthy
                number = inst.number
                name = inst.human_name or inst.project
                role = inst.role
                shard_idx = inst.shard_index
                port = inst.port
                ip = inst.container_ip or ""
            else:
                healthy = inst.get("healthy")
                number = inst.get("number", "?")
                name = inst.get("human_name") or inst.get("project", "?")
                role = inst.get("role", "?")
                shard_idx = inst.get("shard_index")
                port = inst.get("port", "?")
                ip = inst.get("container_ip", "")

            # Health indicator with spinner for healthy nodes
            if healthy is True:
                spinner = _SPINNER_FRAMES[self._frame]
                health_str = f"[bold green]{spinner} ok[/]"
            elif healthy is False:
                health_str = "[bold red]\u25cf down[/]"
            else:
                health_str = "[dim]\u25cb ---[/]"

            # Role display with color
            if role == "orchestrator":
                role_str = "[bold cyan]orchestrator[/]"
            elif role == "shard" and shard_idx is not None:
                role_str = f"[yellow]shard [{shard_idx}][/]"
            elif role == "shard":
                role_str = "[yellow]shard[/]"
            else:
                role_str = f"[dim]{role}[/]"

            # Truncate name to fit
            display_name = str(name)[:14]
            ip_str = str(ip)[:15] if ip else "[dim]pending[/]"

            lines.append(
                f" {number:<3} {display_name:<14} {role_str:<22} "
                f"{port:<6} {ip_str:<15} {health_str}"
            )

        # Cluster summary
        total = len(self._instances)
        healthy_count = sum(
            1 for i in self._instances
            if (i.healthy if hasattr(i, "healthy") else i.get("healthy"))
        )
        shard_count = sum(
            1 for i in self._instances
            if (i.role if hasattr(i, "role") else i.get("role")) == "shard"
        )
        lines.append("")
        lines.append(
            f" [dim]{total} node(s), {shard_count} shard(s), "
            f"{healthy_count}/{total} healthy  |  "
            f"[b]M[/b]:Manage  [b]+[/b]:Spawn[/]"
        )

        content.update("\n".join(lines))


# ---------------------------------------------------------------------------
# Status bar (mainframe-style with single-key hints)
# ---------------------------------------------------------------------------

class StatusBar(Widget):
    """Bottom status bar with pipeline stage and single-key action hints."""

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
            " [b]?[/]:Help  [b]M[/]:Instances  [b]C[/]:Cluster  [b]K[/]:Keys  "
            "[b]N[/]:Nodes  [b]D[/]:Deps  [b]U[/]:Update  [b]S[/]:Setup  "
            "[b]Q[/]:Quit",
            id="status-bar-content",
        )

    def set_stage(self, stage: str) -> None:
        self.query_one("#status-bar-content", Static).update(
            f" [bold yellow]{stage}[/]  |  "
            "[b]?[/]:Help [b]M[/]:Instances [b]C[/]:Cluster [b]K[/]:Keys "
            "[b]N[/]:Nodes [b]U[/]:Update [b]Q[/]:Quit"
        )

    def reset(self) -> None:
        self.query_one("#status-bar-content", Static).update(
            " [b]?[/]:Help  [b]M[/]:Instances  [b]C[/]:Cluster  [b]K[/]:Keys  "
            "[b]N[/]:Nodes  [b]D[/]:Deps  [b]U[/]:Update  [b]S[/]:Setup  "
            "[b]Q[/]:Quit"
        )
