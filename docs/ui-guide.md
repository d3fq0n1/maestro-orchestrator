# UI Guide: Maestro-Orchestrator

## Overview

This guide outlines the structure and behavior of the Maestro-Orchestrator frontend, built with React, Vite, and TailwindCSS.

---

## Stack

* **Framework:** React (Vite)
* **Styling:** TailwindCSS
* **Language:** TypeScript
* **Location:** `frontend/src/maestroUI.tsx`

---

## Layout

* **Prompt Input Field:**
  * Single text box with a submit button
  * Triggers `POST` to `/api/ask`

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

---

## Behavior Flow

```text
User types -> Clicks Submit -> Loading state
-> Agent responses rendered (one per card)
-> Dissent analysis displayed
-> NCG benchmark with drift data
-> Quorum bar with agreement ratio
-> R2 grade with confidence and flags
-> Session persisted to history
```

---

## Features

* **Full Analysis Rendering:** R2 grades, quorum bar, dissent, NCG drift -- all displayed per session
* **Emoji Mapping:** Helps humanize model identity
* **Session History:** Browse past sessions from the UI
* **Key Management:** Configure and validate API keys without editing `.env`
* **Error Handling:** API failure messages shown inline
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
