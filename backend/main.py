from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from orchestrator_foundry import run_orchestration, stream_orchestration
from maestro.api_sessions import router as sessions_router
from maestro.api_magi import router as magi_router
from maestro.api_keys import router as keys_router
from maestro.api_self_improve import router as self_improve_router
from maestro.api_update import router as update_router
from maestro.api_storage import router as storage_router
from maestro.api_plugins import router as plugins_router

# === Initialize FastAPI app ===
app = FastAPI()

# === CORS setup for local development/testing ===
# NOTE: allow_origins=["*"] is acceptable for local/Docker use.
# For production deployments exposed to the internet, restrict this to
# your actual origin(s) via the MAESTRO_ALLOWED_ORIGINS env variable
# or by editing this value directly.
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
app.include_router(self_improve_router)
app.include_router(update_router)
app.include_router(storage_router)
app.include_router(plugins_router)

# === Health check ===
@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/health/dependencies")
async def health_dependencies():
    from maestro.dependency_resolver import resolve_all
    report = resolve_all()
    return report.to_dict()

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
            "agent_errors": result.get("agent_errors", []),
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
        print(f"[Orchestration Error] {type(e).__name__}: {e}")
        return {
            "responses": {},
            "error": f"{type(e).__name__}: {str(e)}",
        }

# === POST endpoint for streaming orchestration (SSE) ===
@app.post("/api/ask/stream")
async def ask_stream(prompt: Prompt):
    user_prompt = prompt.prompt.strip()
    if not user_prompt:
        return {"error": "Prompt cannot be empty or whitespace-only."}

    print(f"[Maestro-Orchestrator] Stream prompt received: {user_prompt}")

    return StreamingResponse(
        stream_orchestration(user_prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# === Static UI Mount (Vite production build) ===
# In Docker, the built frontend is copied to backend/frontend/dist.
# In local dev, the frontend runs its own Vite dev server instead.
ui_path = Path(__file__).parent / "frontend" / "dist"
if ui_path.exists():
    app.mount("/", StaticFiles(directory=ui_path, html=True), name="static")
else:
    print(f"[Maestro] UI build not found at {ui_path} -- running in API-only mode")

    @app.get("/")
    async def fallback_root():
        return {
            "status": "api-only",
            "message": "Maestro-Orchestrator is running but the UI build is missing. "
                       "Rebuild the Docker image to restore the frontend, or use the API directly.",
            "health": "/api/health",
            "ask": "/api/ask",
        }
