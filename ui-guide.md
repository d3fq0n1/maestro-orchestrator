# UI Guide: Maestro-Orchestrator

This guide documents the user interface layer of Maestro-Orchestrator, which is built using React (Vite), styled with TailwindCSS, and communicates directly with the FastAPI backend via `fetch("/api/ask")`.

---

## 🧰 Installation

Ensure you are inside the `ui/` directory:

```bash
cd ui
npm install
```

Then start the development server:

```bash
npm run dev
```

The UI will be served at:

```
http://localhost:5173
```

> CORS is already enabled by the backend to allow local development.

---

## 🖥️ Interface Overview

### Prompt Input

- Located at the top of the interface.
- User enters a natural language prompt.
- On submit, the input is sent to `/api/ask`.

### Agent Response Feed

- Displays each AI agent’s response individually.
- Each agent is shown with a unique emoji for identification:
  - `🧠` Sol (OpenAI)
  - `🌱` Aria (Claude)
  - `🌈` Prism (Gemini)
  - `🔮` TempAgent (OpenRouter)

### Quorum Summary

- Below the agent responses, a consensus result is displayed:
  - If quorum is reached → shows consensus output.
  - If not → shows “No consensus” with dissenting opinions preserved.

### Error Handling

- If the API returns an error, a fallback message appears below the input bar.
- API issues will not break the UI — the input resets and user can try again.

---

## 📦 File Structure

```
ui/
├── index.html                 # Root template
└── src/
    ├── maestroUI.tsx         # Main React component
    └── components/           # (Optional) reusable UI components
```

---

## 🔮 Future Features

Planned UI additions for v0.3+:

- Session log viewer
- Toggleable agent filters
- Real-time MAGI diagnostics overlay
- Capsule state comparison tools

---

Built with intention. No fluff, no dark patterns.
