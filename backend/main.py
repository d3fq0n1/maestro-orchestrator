from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from orchestrator_foundry import run_orchestration

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
        return result

    except Exception as e:
        print(f"[ERROR] {e}")
        return {
            "responses": {
                "Sol": "⚠️ Error processing request.",
                "Aria": "",
                "Prism": "",
                "TempAgent": ""
            },
            "quorum": {
                "consensus": "❌ Failed",
                "votes": {}
            }
        }

# === Static UI Mount (Vite production build) ===
ui_path = Path(__file__).parent / "frontend" / "dist"
if not ui_path.exists():
    raise RuntimeError(f"⚠️ UI build output not found at: {ui_path}")

app.mount("/", StaticFiles(directory=ui_path, html=True), name="static")

# === Optional: direct GET fallback ===
@app.get("/")
async def serve_index():
    index_path = ui_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "index.html not found in dist/"}
