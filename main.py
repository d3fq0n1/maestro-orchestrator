from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from orchestrator_foundry import run_orchestration

# === Initialize FastAPI app ===
app = FastAPI()

# === CORS setup for local development ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Request model ===
class Prompt(BaseModel):
    prompt: str

# === POST endpoint for orchestration ===
@app.post("/api/ask")
async def ask(prompt: Prompt):
    print(f"[Maestro-Orchestrator] Prompt received: {prompt.prompt}")

    try:
        result = await run_orchestration(prompt.prompt)
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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Serve the Vite-built UI from /ui/dist
app.mount("/", StaticFiles(directory="ui/dist", html=True), name="static")

# Optional: direct index.html fallback
@app.get("/")
async def serve_index():
    return FileResponse("ui/dist/index.html")
