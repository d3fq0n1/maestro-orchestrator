# Maestro-Orchestrator v7.4.0

**Multi-Agent AI Orchestration with Synthetic Consensus, Deliberation, and Dissent**

---

## What's New in v7.4.0

### Boot Progress Bar Fix

The setup progress bar used an asymptotic exponential curve that crawled at 1-3%
for the entire wait and then jumped to completion. Replaced with a two-phase linear
ramp: 0→80% over the estimated duration, then a gentle ease toward 95% if the build
runs long. The bar now gives accurate, reassuring visual feedback throughout the
entire boot sequence.

### Deliberation Visual Feedback (TUI)

The TUI previously showed zero visual activity during multi-round deliberation —
the `deliberation_start`, `deliberation_round`, and `deliberation_done` SSE events
were silently dropped. Now:

- **`deliberation_start`** — Status bar shows "Deliberation: round 1/N", agent
  indicators reset to running (spinning), response viewer logs the start.
- **`deliberation_round`** — Each completed round flips agent indicators to "done",
  status bar and response viewer show round progress.
- **`deliberation_done`** — Summary logged (rounds completed, agents participated),
  or skip reason if deliberation was bypassed.

### Prompt Screen Pipeline Preview

The Prompt screen (`P` key) now includes a bordered **Pipeline Preview** panel
below the deliberation controls, showing:

- Agent roster (GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B)
- Deliberation status (ON/OFF, round count) — updates reactively as you toggle
- Analysis pipeline stages (Dissent → NCG → Consensus → R2)

This makes the prompt screen visually richer and immediately communicates what
will happen when you press Enter.

---

## What's New in v7.3.0

### Session History Browser (H key)

Pressing `H` now opens a full-screen **Session Browser** modal instead of dumping
a summary to the response log. The browser includes:

- **Session list panel** — shows up to 9 recent sessions with ID, timestamp, prompt
  preview, agent count, and NCG status. Press `1-9` to select and load a session.
- **Full detail view** — scrollable RichLog showing complete session content:
  agent responses, consensus output, agreement/quorum metrics, dissent analysis,
  R2 grade with flags, NCG benchmark with drift values, and full deliberation
  round-by-round history showing how each agent's position evolved.
- **Re-run support** — press `R` to re-open the selected session's prompt in the
  Prompt screen for re-orchestration.

### Improved Prompt Screen controls

- **Radio buttons** — removed the blocky colored indicator blocks from the
  deliberation round selector. Round buttons now display as clean text labels
  with accent color highlighting for the selected option.
- **Switch styling** — deliberation toggle switch uses transparent background
  with muted/success color states instead of default block styling.

### Self-Improvement now functional (I key)

The `I` key binding now runs a real self-improvement cycle using the
`SelfImprovementEngine`, displaying MAGI analysis results, generated proposals,
and VIR validation status in the response viewer. Previously this was a
placeholder message.

### Backend session detail API

- `MaestroBackend.get_session_detail(session_id)` — new abstract method for
  loading full session records by ID.
- Implemented in both `DirectBackend` (loads from disk via `SessionLogger`) and
  `HTTPBackend` (fetches from `/api/sessions/{id}`).

---

## What's New in v7.2.8

### Dedicated Prompt Screen (P key)

Pressing `P` now opens a full-screen modal prompt interface instead of focusing a
cramped bottom input bar. The new Prompt screen includes:

- **Session history panel** — shows recent sessions with ID, prompt preview, and R2
  grade. Press `1-9` to re-run a past prompt.
- **Prompt templates** — built-in templates loadable via `F1-F5`, with `Ctrl+S` to
  save the current prompt as a new template. Templates persist to
  `data/prompt_templates.json`.
- **Deliberation controls** — visual toggle switch (`T` to toggle ON/OFF) and
  radio-button round selector (`R` to cycle 1-5). Parameters pass through the
  backend to `run_orchestration_stream()`.

The old 3-line bordered input widget is replaced with a minimal 1-line hint bar,
reclaiming vertical space for the response viewer.

### Backend deliberation parameter passthrough

Both `DirectBackend` and `HTTPBackend` now accept `deliberation_enabled` and
`deliberation_rounds` parameters in `orchestrate()`, forwarding them to the
orchestration pipeline.

---

## What's New in v7.2.7

### Bug Fix: "No API keys configured" shown despite keys being set

When the TUI was launched in HTTP mode (`--mode http`), the first-run detection
routine read API key status directly from `os.environ` without first loading the
`.env` file. Because `DirectBackend.__init__` (which calls `_load_env`) is never
instantiated in HTTP mode, the environment was always empty and the TUI incorrectly
displayed "No API keys configured" even when keys were present on disk.

**Fix:** `_check_first_run()` now calls `_load_env()` unconditionally before
inspecting key status, so the `.env` file is always sourced regardless of backend
mode.

### TUI header now shows version number

The sub-title of the Textual dashboard now includes the current version string
(`v7.2.7 | TUI Dashboard`), making it immediately visible at the top of every
TUI session.

### Version canonicalized in `maestro/__init__.py`

`__version__ = "7.2.7"` is now the single authoritative source; `_MAESTRO_VERSION`
in `plugins/manager.py` and the FastAPI `version=` in `node_server.py` are updated
to match.

---

## What's New in v7.2.6

### Bug Fix: 4th+ cluster node spawn fails with "ambiguous network" error

Spawning a cluster node into a slot that previously held a crashed or partially torn-down node could fail with:

```
Spawn failed: Failed to start maestro-4: 2 matches found based on name:
network maestro-4_maestro-net is ambiguous
```

**Root cause:** `compose down` sometimes removes containers but leaves the bridge network behind (e.g. when another container is transiently attached). On the next spawn of the same slot, Docker Compose finds both the leftover network and the one it is about to create — causing the ambiguity error.

**Fix:** The spawn pre-flight (`_cleanup_stale_project`) now uses `docker network ls --filter name=...` to enumerate **all** matching network IDs and removes each by ID, so duplicates cannot survive to block the next start.

### Previous fixes (v7.2.5)

- **TUI update auto-restart (CRITICAL)** — Applying an update in the TUI now shows "Update applied. Restarting in 3 seconds..." and automatically replaces the process via `os.execv`, preserving the terminal session. Previously it printed a manual restart message and did nothing.
- **DOM mutation race condition (CRITICAL)** — `action_check()` ran on a background worker thread and called DOM methods directly without `call_from_thread`. Fixed.
- **`asyncio.get_event_loop()` deprecation (HIGH)** — Six occurrences across `updater.py`, `lan_discovery.py`, and `api_instances.py` replaced with `asyncio.get_running_loop()`.
- **Temp directory leak (HIGH)** — `_apply_docker_mode()` now wraps its clone+copy body in `try/finally` so the temp directory is always cleaned up.
- **Docker build output corruption (MEDIUM)** — `_maybe_rebuild()` now uses `capture_output=True` to prevent Docker output from bleeding into the Textual terminal.
- **Thread pool churn (LOW)** — `_refresh_cluster_dashboard()` no longer creates and destroys a `ThreadPoolExecutor` every 5 seconds; it now uses the default shared executor.

---

## What was new in v7.2.4

### Boot Loading Animation

Startup no longer dumps raw pip output and status vomit to the terminal. The pre-launch sequence (dependency resolution, update checks, module imports) now runs behind a **bouncing-ball loading animation** that keeps the terminal clean.

- `entrypoint.py` wraps dependency install + update check behind a single animated line
- `maestro/cli.py` shows a loader during the heavy import phase (agents, orchestrator, NCG generators)
- `setup.py` installs missing packages quietly (pip output suppressed)

### Emoji Purge

All decorative emoji characters (`✓`, `⚠`, `♫`, `✔`, `✘`, `⚡`, `◈`, `◉`, `◎`) removed from source code and replaced with plain ASCII equivalents (`[ok]`, `[!!]`, `[x]`, `>`, `--`). Status glyphs in the TUI (`\u2714`, `\u2718`, `\u2726`) also replaced. Functional Unicode characters (Braille spinners, box-drawing, geometric indicators used by the Textual TUI) are unchanged.

---

## What was new in v7.2.3

### Dependency Health Check Fix

The dependency health check now accurately reflects the true state of your environment **and** automatically installs missing Python packages at startup.

**What was wrong:**

- `setup.py` printed "Dependencies verified" after only checking for Docker — Python packages were never verified
- The health check correctly detected missing packages (openai, anthropic, pydantic, etc.) but nothing acted on the results
- Running `entrypoint.py` directly (without Docker or `setup.py --dev`) skipped dependency installation entirely

**What's fixed:**

- New `ensure_packages()` in the dependency resolver auto-installs any missing required Python packages via pip
- `setup.py` now verifies Python packages after Docker verification and after `pip install -r requirements.txt` in dev mode
- `entrypoint.py` installs missing packages before launching any mode (web/cli/tui)
- The misleading "Dependencies verified" message now reads "Docker verified" and "Python packages verified" separately
- PEP 668 (externally-managed-environment) fallback for Debian/Ubuntu systems

---

## What was new in v7.2.2

### Cluster-Aware Instance Spawning

Pressing `+` in the TUI Instance screen now spawns **fully functional shard/node cluster members** that see each other as peers. No more isolated Docker stacks — each instance is a real member of a Maestro cluster.

**How it works:**

1. Press `M` to open the Instance manager, then `+` to spawn
2. The first instance becomes the **orchestrator** (coordinator)
3. Every subsequent instance spawns as a **shard worker** with an auto-assigned shard index
4. All instances share a Docker network and Redis state bus, so they discover each other automatically
5. Each instance gets a human-readable name (e.g. "swift-falcon", "bold-eagle")
6. Container IPs, roles, and health are displayed in the TUI dashboard

**Instance table now shows:**

```
  #    Name             Role          Port    IP               Health
  ──── ──────────────── ───────────── ─────── ──────────────── ──────────
  1    bold-eagle       orchestrator  8000    172.18.0.2       ● healthy
  2    swift-fox        shard [0]     8010    172.18.0.3       ● healthy
  3    calm-owl         shard [1]     8020    172.18.0.4       ● healthy

  Cluster: 3 node(s), 2 shard(s), 3/3 healthy
```

**Technical details:**
- Shared Docker network (`maestro-cluster-net`) for inter-node communication
- Shared Redis container (`maestro-shared-redis`) for cluster state bus
- Persistent instance registry (`.maestro-instances.json`) survives TUI restarts
- Topology broadcast to Redis on every spawn/stop so all nodes see changes
- Thread-safe TUI updates via `call_from_thread`

---

## What was new in v7.1.6

### TUI Node Detail Crash Fix

Fixed `AttributeError: 'list' object has no attribute '_append'` that crashed the TUI when pressing `N` (Nodes). The `NodeDetailScreen` modal was storing its node data as `self._nodes`, which overwrote Textual's internal `_nodes` attribute (a `NodeList` used for the widget tree). Renamed to `self._node_data` to avoid the collision — the same class of bug that was previously fixed in `ShardNetworkPanel` (v0.7.2).

---

## What was new in v7.1.5

### Automatic Background Updater

The auto-updater now runs as a **background task** in both the TUI and WebUI, seamlessly pulling git updates while you work. Designed for iterative development where you're actively pushing fixes and testing.

**How it works:**

1. Set `MAESTRO_AUTO_UPDATE=1` in your `.env` (or toggle it in the UI)
2. The updater polls git every 60 seconds (configurable from 15s to 10m)
3. When updates are detected, you get a live notification — in the WebUI as a banner, in the TUI as a response viewer message
4. Optionally enable `MAESTRO_AUTO_APPLY_UPDATES=1` to auto-pull without confirmation

**WebUI features:**
- Live notification banner powered by Server-Sent Events (no polling)
- Auto-update controls in the Update panel: toggle auto-check, toggle auto-apply, interval selector
- All settings persisted to `.env`

**TUI features:**
- Background update loop with event-driven notifications
- Press `U` to open the update screen, `T` to toggle auto-update on/off
- Status bar shows enabled state, interval, and applied count

**New API endpoints:**
- `GET /api/update/stream` — SSE stream of real-time update events
- `GET /api/update/auto` — auto-updater status
- `PUT /api/update/auto` — configure auto-updater on the fly

**New environment variables:**
- `MAESTRO_UPDATE_INTERVAL` — poll interval in seconds (default 60, min 10)
- `MAESTRO_AUTO_APPLY_UPDATES` — set to `1` to auto-apply

### What was new in v7.1.4

The Storage Network panel gained a **LAN Discovery** tab, the TUI Pipeline panel now shows correct model names, and documentation was updated for consistency.

### What was new in v0.7.2

### Interactive Mode Selector

No more memorizing `python -m maestro.tui --mode http` or `python -m maestro.cli`. After Docker setup completes (or when the startup wrapper runs without `dialog`), Maestro now shows a **fancy arrow-key selector** — navigate with Up/Down, press Enter to launch:

- **TUI Dashboard** — Terminal dashboard optimized for SoC / Raspi
- **Interactive CLI** — Command-line REPL with full pipeline access
- **Web UI** — Full dashboard (API + React UI)

The selector uses ANSI colors and highlights, falls back to a numbered prompt on non-interactive terminals, and works everywhere Python runs.

### TUI Crash Fix

Fixed `AttributeError: 'list' object has no attribute '_append'` that prevented the TUI from launching. The `ShardNetworkPanel` widget was accidentally overwriting Textual's internal `_nodes` attribute.

---

## Highlights from v0.7.1

### Model Deliberation

Agents no longer respond in isolation. After all agents return their initial answers, the **Deliberation Engine** feeds each agent's response back into the pool — every agent reads what its peers said and produces a refined reply before any analysis runs.

- **Default on** — deliberation runs automatically with 1 round unless you opt out via `deliberation_enabled: false` in the API request.
- **Configurable rounds** — set `deliberation_rounds` (1–5) to run multiple passes of cross-agent debate. Each round costs one additional API call per agent.
- **Non-fatal** — if any agent errors during deliberation, it keeps its previous response and the pipeline continues.
- **Full history** — the API response includes a `deliberation` summary (rounds completed, participating agents). The streaming endpoint emits per-round responses as they arrive.
- **Downstream analysis operates on deliberated positions** — dissent analysis, NCG drift detection, and quorum aggregation all run on the agents' considered, post-deliberation outputs.

**API changes (both `/api/ask` and `/api/ask/stream`):**

```json
{
  "prompt": "Your question here",
  "deliberation_enabled": true,
  "deliberation_rounds": 1
}
```

Both new fields are optional. The default behaviour (`deliberation_enabled: true, deliberation_rounds: 1`) requires no changes to existing integrations.

**New SSE events (streaming endpoint):**

| Event | Description |
|-------|-------------|
| `deliberation_start` | Deliberation beginning — round count and agent list |
| `deliberation_round` | One round complete — round number and all per-agent deliberated responses |
| `deliberation_done` | All rounds finished — summary with participation and any skip reason |

---

## Highlights from v0.7.0

### TUI Dashboard

- **Full Textual-based terminal dashboard** optimized for SoC devices (Raspberry Pi 5). Agent panel with live status indicators, consensus metrics, response viewer with syntax highlighting, shard network monitor, modal screens (F1 help, F2 node detail, F3 API key status).
- **Dual backend modes** — Direct import (in-process, lowest latency) and HTTP client (connects to running server via SSE, supports multi-device clusters).
- **TUI mode in startup wrapper** — `entrypoint.py` now offers TUI as a third option alongside Web-UI and CLI. Selectable via dialog menu or `MAESTRO_MODE=tui`.

### Setup Improvements

- **Graceful Docker fallback** — `setup.py` now suggests `--dev` mode when Docker is not installed, with an interactive prompt to switch automatically. No more hard failure on systems without Docker.

---

## Highlights from v0.6.3

### Storage Network Dashboard

Full GUI for visualizing the distributed storage network, accessible via the **Storage** button in the Web-UI header:

- **Network tab** — Per-model mirror status, layer coverage bars, inference pipeline visualization, redundancy map, gap detection
- **Shard Map tab** — Visual grid of nodes × layer blocks with color-coded coverage and redundancy indicators
- **Network topology API** (`GET /api/storage/network/topology`) — Full network state in a single call

### Shard Management API

- Download model shards from HuggingFace Hub, track progress, verify integrity, report disk usage, and generate `node_shards.json` configs via `/api/storage/shards/*`

---

## Highlights from v0.6.2

- **Shard utilities** — Header parsing, layer index extraction, byte-range SHA-256 proofs, and shard descriptor generation for safetensors weight files
- **Shard Manager** — Download, index, verify, and manage local weight shards; integrates with HuggingFace Hub
- **Node CLI** — `python -m maestro.node_cli` for storage node operators (setup, start, status, verify, shards)
- **Real byte-range proof challenges** — Node server hashes actual file bytes when shards are on disk
- **Node auto-registration** — Node server registers with the orchestrator and sends heartbeats automatically

---

## Highlights from v0.6.1

- **Update progress bar** — Visual feedback while updates are applied
- **Restart server button** — One-click restart after a successful update
- **Default remote URL** — Auto-updater now defaults to the canonical GitHub repo
- **Bug fixes** — API keys preserved across updates, duplicate error prefixes removed, `Errno 17` on update resolved

---

## Highlights from v0.6

### Proof-of-Storage Distributed Inference

Full storage network layer enabling distributed model inference across storage nodes:

- **Storage Node Registry** — Shard-aware topology, pipeline construction, redundancy mapping, heartbeat tracking, reputation integration
- **Storage Proof Engine** — Three proof types: Proof-of-Replication (byte-range hash), Proof-of-Residency (latency probe), Proof-of-Inference (canary inference)
- **Reputation Scoring** — `0.7 × challenge_pass_rate + 0.3 × R2_contribution`. Automatic eviction below threshold.
- **ShardAgent** — Distributed inference agent with the same `fetch(prompt) -> str` interface as centralized agents
- **Node Server** — Standalone FastAPI server for storage nodes. Endpoints: `/infer`, `/challenge`, `/health`, `/heartbeat`, `/shards`

### Modular Plugin Architecture (Mod Manager)

Complete plugin system for extending Maestro without modifying core code:

- **Plugin Protocol** — `MaestroPlugin` ABC with `activate()`, `deactivate()`, `health_check()`, and `on_config_change()`
- **Full Lifecycle** — Discover, validate, load, enable, disable, unload, hot-reload
- **8 Pipeline Hooks** — `pre_orchestration`, `post_agent_response`, `pre_aggregation`, `post_aggregation`, `pre_r2_scoring`, `post_r2_scoring`, `pre_session_save`, `post_session_save`
- **Event Bus** — Inter-plugin pub/sub with error isolation
- **PluginContext** — Controlled access to Maestro internals (registry, R2, session logger, agent registration, hooks, events)

### Weight State Snapshots

Save, restore, diff, and delete system configuration snapshots capturing plugin states, active agents, thresholds, and runtime config overlay.

---

## Agent Council

| Agent | Model | Role |
|-------|-------|------|
| GPT-4o | `gpt-4o` (OpenAI) | Primary reasoning engine |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` (Anthropic) | Contextual analysis |
| Gemini 2.5 Flash | `models/gemini-2.5-flash` (Google) | Pattern-focused, low latency |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` (OpenRouter) | Diversity anchor (open-weight) |
| ShardNet | `distributed` (Storage Network) | Proof-of-storage distributed inference |

---

## Quick Start

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python setup.py        # Windows, macOS, Linux — just needs Python + Docker
```

On macOS/Linux you can also use `make setup`.

API keys can be configured through the Web UI — no `.env` file required.

---

## Full Changelog

See [changelog.md](changelog.md) for the complete version history.
