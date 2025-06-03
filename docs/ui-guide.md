# 🎨 UI Guide: Maestro-Orchestrator

## Overview

This guide outlines the structure and behavior of the Maestro-Orchestrator frontend, built with React, Vite, and TailwindCSS.

---

## 🖥️ Stack

* **Framework:** React (Vite)
* **Styling:** TailwindCSS
* **Language:** TypeScript
* **Location:** `ui/src/maestroUI.tsx`

---

## 🧭 Layout

* **Prompt Input Field:**

  * Single text box with a submit button
  * Triggers `POST` to `/api/ask`

* **Agent Response Section:**

  * Displays all agent responses in vertical list
  * Includes emoji, agent name, and response text

* **Consensus Indicator:**

  * Renders when 2 or more agents match
  * Shows count and brief summary of matched output

* **Dissent Log:**

  * Below consensus area
  * Displays unique or minority views from agents

---

## 🔁 Behavior Flow

```text
User types → Clicks Submit → Loading state
→ Agent responses stream in (one per card)
→ Quorum logic analyzed
→ Consensus + Dissent rendered
```

---

## 💡 Features

* **Live Render:** UI updates incrementally as each agent replies
* **Emoji Mapping:** Helps humanize model identity
* **Error Handling:** API failure messages shown inline
* **Local Dev Support:** Fully CORS-compliant for FastAPI

---

## 🛠️ Planned Improvements

* Session history viewer (linked CLI + UI timeline)
* Response voting & reinforcement (via R2 Engine)
* Mobile layout refinements
* Loading animation per agent

---

## 🚧 Dev Notes

To launch UI:

```bash
cd ui
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` and sends requests to `http://localhost:8000/api/ask`

Ensure backend (`main.py`) is running simultaneously via `uvicorn`.
