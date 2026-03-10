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
  * Includes emoji, agent name, and response text

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
* **Emoji Mapping:** Helps humanize model identity
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

Frontend runs on `http://localhost:5173` and sends requests to `http://localhost:8000/api/ask`

Ensure backend (`backend/main.py`) is running simultaneously via `uvicorn backend.main:app --reload --port 8000`.
