# UI Guide: Maestro-Orchestrator

## Overview

This guide outlines the structure and behavior of the Maestro-Orchestrator frontend, built with React and Vite.

---

## Stack

* **Framework:** React (Vite)
* **Styling:** CSS (`frontend/src/style.css`)
* **Language:** TypeScript
* **Location:** `frontend/src/maestroUI.tsx`

---

## Layout

* **Prompt Input Field:**
  * Single text box with a submit button
  * Triggers `POST` to `/api/ask/stream` (SSE streaming)

* **R2 Session Grade:**
  * Displays session quality grade (strong/acceptable/weak/suspicious)
  * Shows confidence score and any flags detected

* **Quorum Bar:**
  * Agreement ratio visualization with 66% threshold indicator
  * Shows whether quorum was met

* **Agent Response Section:**
  * Displays all agent responses in vertical list
  * Includes agent marker, agent name, and response text

* **Dissent Analysis:**
  * Pairwise semantic distances between agents (expandable)
  * Outlier detection and internal agreement score

* **NCG Benchmark:**
  * Per-agent drift from headless baseline
  * Silent collapse warnings when detected

* **Session History Browser:**
  * Browse and review past orchestration sessions

* **API Key Configuration Panel:**
  * Configure, validate, and update API keys in-app

* **Storage Network Panel:**
  * **Network tab** — Full network topology showing which nodes contribute shards to each model, mirror completeness status (full mirror when all layers covered), inference pipeline visualization with hop ordering, neighbor node listing with reputation/latency, redundancy map showing how many nodes hold each layer range, layer coverage bar with visual gap detection. Empty states show a copyable CLI command with the current orchestrator URL
  * **Shard Map tab** — Visual grid of nodes vs layer blocks showing shard distribution across the network, per-node color-coded coverage, aggregate network coverage row with redundancy indicators (green = 2x+, yellow = 1x, red = gap)
  * **Nodes tab** — List of registered storage nodes with status tags (available/busy/probation/offline/evicted), reputation percentages, latency, shard pills, heartbeat timestamps, challenge and remove actions. Empty states show a copyable CLI command with the current orchestrator URL
  * **Shards tab** — Download form for HuggingFace model shards with layer range selection, live download status polling, per-model cards showing layer coverage, completeness, precision, file count, disk usage, verify/generate-config/remove actions
  * **LAN Discovery tab** — Shows the local shard identity, Maestro Node formation status (formed/not formed with member count), and discovered LAN peers with adjacency state (confirmed/handshake/discovered/offline), latency, and alive indicators. Surfaces the same data as the TUI's LAN Discovery panel

* **Cluster Instance Panel:**
  * View all running Maestro instances with health status, role (orchestrator/shard), port, and container IP
  * Spawn new cluster members (first becomes orchestrator, additional join as shard workers)
  * Stop individual instances or view the cluster summary
  * Matches the TUI's Instance Manager (`M` key) functionality

* **System Update Panel:**
  * Check for updates from the configured remote repository
  * View new commits available with one-line summaries
  * Apply updates with an indeterminate progress bar during the process
  * Configurable remote repository URL (defaults to `https://github.com/d3fq0n1/maestro-orchestrator.git`)
  * Red "Restart server" button after a successful update to reload changes

---

## Behavior Flow

```text
User types -> Clicks Submit (or Enter) -> Loading state
-> SSE stream opens to /api/ask/stream
-> Stage indicators update in real-time (pipeline progress pills)
-> Agent responses stream in progressively (one per card)
-> Dissent analysis displayed
-> NCG benchmark with drift data
-> Consensus + quorum bar with agreement ratio
-> R2 grade with confidence and flags
-> Stream completes -> session finalized to history
```

---

## Features

* **Real-time SSE Streaming:** Agent responses and pipeline stages arrive progressively via Server-Sent Events
* **Full Analysis Rendering:** R2 grades, quorum bar, dissent, NCG drift -- all displayed per session
* **Agent Markers:** Color-coded agent identity indicators
* **Session History:** Browse past sessions from the UI
* **Key Management:** Configure and validate API keys without editing `.env`
* **Storage Network:** Full shard distribution, node topology, and mirror completeness visualization with copyable CLI commands
* **System Update:** Check, apply, and restart from the UI with progress feedback
* **Error Handling:** Contextual HTTP error messages (404, 429, 401/403, 5xx, 422) shown inline
* **Local Dev Support:** Fully CORS-compliant for FastAPI

---

## Dev Notes

To launch UI:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` and sends requests to `http://localhost:8000/api/ask/stream`

Ensure backend (`backend/main.py`) is running simultaneously via `uvicorn backend.main:app --reload --port 8000`.

---

## TUI Dashboard (Raspberry Pi 5 / SoC)

### Overview

The TUI is a Textual-based terminal dashboard designed for SoC devices like the Raspberry Pi 5. It provides the full orchestration experience in a terminal interface optimized for 80x24 minimum displays. Navigation is **mainframe-style** — most actions are bound to a single keypress so you never need to type long commands.

### Stack

* **Framework:** Textual + Rich
* **Language:** Python
* **Location:** `maestro/tui/`

### Launch

```bash
python -m maestro.tui                          # Direct import mode
python -m maestro.tui --mode http              # HTTP client to localhost:8000
python -m maestro.tui --mode http --url URL    # HTTP client to remote server
MAESTRO_MODE=tui python entrypoint.py          # Via startup wrapper
```

### First-Run Setup

On first launch the TUI detects that no API keys are configured and automatically opens the **Setup Wizard** (`S` key). The wizard walks through each provider (OpenAI, Anthropic, Google, OpenRouter), shows where to get a key, and lets you paste it directly. Keys are validated in real-time and saved to `.env`.

Tips for entering keys:
* Copy the key from your provider's dashboard
* Right-click or `Ctrl+Shift+V` to paste in most terminals
* Press `Enter` to save, `Tab` to skip a provider, `Escape` to close
* Keys are saved locally to `.env` and never leave your machine

### Layout

* **Header:** Application title and clock
* **Agent Panel (top-left):** Live status indicators for each agent in the council (ready/running/done/error)
* **Consensus Panel (top-right):** Real-time metrics -- agreement ratio, quorum status, confidence level, dissent level, R2 grade, NCG drift
* **Response Viewer (center):** Scrollable log showing agent responses and consensus output as they stream in
* **Cluster Dashboard:** Always-visible live monitor of running cluster instances with BTOP-style spinning health indicators, color-coded roles (cyan orchestrator, yellow shards), port/IP info, and a cluster summary line. Auto-refreshes every 5 seconds. Press `C` to force refresh or `M` to open the full management screen
* **LAN Discovery Panel:** Shows local shard identity, Maestro Node formation status, and discovered LAN peers with adjacency indicators
* **Shard Network Panel:** BTOP-style view of storage nodes with spinning green asterisk indicators for connected nodes, red indicators for offline/missing nodes, memory usage bars, and reputation scores
* **Prompt Input:** Text input for submitting prompts (press `P` to focus)
* **Status Bar:** Current pipeline stage and single-key action hints

### Single-Key Actions (Mainframe-Style)

Press these keys anywhere (except when typing in the prompt input):

| Key | Action |
|-----|--------|
| `?` | Help screen (quick reference) |
| `S` | API key setup wizard |
| `K` | Show API key status |
| `M` | Manage instances (spawn / stop) |
| `+` | Quick-spawn a new cluster shard |
| `C` | Refresh cluster dashboard |
| `N` | Shard network / node details |
| `D` | Dependency health check |
| `H` | Recent session history |
| `U` | Check for updates |
| `L` | Clear response log |
| `P` | Focus the prompt input |
| `Q` | Quit |

Function keys still work as alternatives: `F1` (help), `F2` (nodes), `F3` (keys), `F4` (deps), `F5` (improve), `F6` (update), `Ctrl+L` (clear), `F10` (quit).

### Prompt Commands

Slash commands are still supported for power users when the prompt input is focused:

| Command | Action |
|---------|--------|
| `/nodes` | List storage nodes |
| `/keys` | Show API key status |
| `/setup` | Run the API key setup wizard |
| `/shards` | Show LAN shard discovery status |
| `/history` | Recent session history |
| `/deps` | Dependency health check |
| `/update` | Check for updates |
| `/cluster` | Refresh cluster dashboard |
| `/clear` | Clear response log |
| `/quit` | Exit the TUI |

### Backend Modes

The TUI supports two connection modes:

1. **Direct import** (default): The TUI imports orchestrator modules directly and runs everything in a single process. Best for single-device setups where the TUI runs on the same machine as Maestro.

2. **HTTP client**: The TUI connects to a running Maestro FastAPI server via HTTP and consumes the SSE streaming endpoint for progressive updates. Best for multi-device clusters or when the server runs on a different machine.

### Behavior Flow

```text
User types prompt -> Enter -> Agent panel shows "running"
-> SSE events stream in (direct import or HTTP)
-> Agent indicators flip to "done" as each responds
-> Response viewer shows agent text progressively
-> Consensus panel updates with agreement/quorum/R2/dissent/NCG
-> Consensus text appears in response viewer
-> Status bar shows "Done"
```
