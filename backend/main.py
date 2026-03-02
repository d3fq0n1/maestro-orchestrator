from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from orchestrator_foundry import run_orchestration
from maestro.api_sessions import router as sessions_router
from maestro.api_magi import router as magi_router

import os

# === Initialize FastAPI app ===
app = FastAPI()

# === CORS setup for local development/testing ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Mount API routers ===
app.include_router(sessions_router)
app.include_router(magi_router)

# === Request model ===
class Prompt(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)

# === POST endpoint for orchestration ===
@app.post("/api/ask")
async def ask(prompt: Prompt):
    user_prompt = prompt.prompt.strip()
    if not user_prompt:
        return {"error": "Prompt cannot be empty or whitespace-only."}

    print(f"[Maestro-Orchestrator] Prompt received: {user_prompt}")

    try:
        result = await run_orchestration(user_prompt)

        # Normalize response shape: the frontend reads "responses" as a
        # dict keyed by agent name, and the analysis pipeline returns
        # "named_responses" for that. Merge both into a single envelope
        # that carries the full analysis alongside legacy fields.
        final = result.get("final_output", {})
        return {
            "responses": result.get("named_responses", {}),
            "session_id": result.get("session_id"),
            "consensus": final.get("consensus"),
            "confidence": final.get("confidence"),
            "agreement_ratio": final.get("agreement_ratio"),
            "quorum_met": final.get("quorum_met"),
            "quorum_threshold": final.get("quorum_threshold"),
            "dissent": final.get("dissent"),
            "ncg_benchmark": final.get("ncg_benchmark"),
            "r2": final.get("r2"),
            "note": final.get("note"),
        }

    except Exception as e:
        print(f"[ERROR] {e}")
        return {
            "responses": {},
            "error": str(e),
        }

# === Static UI Mount (Vite production build) ===
ui_path = Path(__file__).parent / "frontend" / "dist"
if not ui_path.exists():
    raise RuntimeError(f"UI build output not found at: {ui_path}")

app.mount("/", StaticFiles(directory=ui_path, html=True), name="static")

# === Optional: direct GET fallback ===
@app.get("/")
async def serve_index():
    index_path = ui_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "index.html not found in dist/"}
