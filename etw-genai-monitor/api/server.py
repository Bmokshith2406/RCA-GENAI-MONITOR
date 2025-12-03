import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.state import STATE
from src.monitor_loop import run_monitor_loop
from src.utils.logger import log

app = FastAPI(title="ETW GenAI Kernel Monitor API")

# -------------------------------------------------
# CORS
# -------------------------------------------------

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,     # ✅ recommended
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Startup
# -------------------------------------------------

@app.on_event("startup")
async def startup_event():
    log("API startup: launching monitor loop in background thread")
    asyncio.create_task(asyncio.to_thread(run_monitor_loop))

# -------------------------------------------------
# Routes
# -------------------------------------------------

@app.get("/api/spikes")
def get_spikes():
    return {"spikes": STATE.get_spikes()}


@app.get("/api/latest-rca")
def get_latest_rca():
    return {"latest_rca": STATE.get_latest_rca()}


@app.get("/api/spikes/{spike_id}")
def get_spike(spike_id: int):
    spike = STATE.get_spike(spike_id)

    if not spike:
        raise HTTPException(
            status_code=404,
            detail=f"Spike with id={spike_id} not found"
        )

    return spike


@app.get("/api/events")
def get_events(limit: int = 200):
    return {
        "events": STATE.get_events(limit)
    }
