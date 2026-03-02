from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from orchestrator_foundry import run_orchestration
from maestro.api_sessions import router as sessions_router
from maestro.api_magi import router as magi_router
from maestro.api_keys import router as keys_router

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
app.include_router(keys_router)

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
# In Docker, the built frontend is copied to backend/frontend/dist.
# In local dev, the frontend runs its own Vite dev server instead.
ui_path = Path(__file__).parent / "frontend" / "dist"
if ui_path.exists():
    app.mount("/", StaticFiles(directory=ui_path, html=True), name="static")
else:
    print(f"[Maestro] UI build not found at {ui_path} -- running in API-only mode")
