import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.monitor_loop import run_monitor_loop
from src.state import STATE
from src.utils.logger import log


# -------------------------------------------------
# ✅ LIFESPAN (CLEAN STARTUP / SHUTDOWN HANDLING)
# -------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log("API startup: launching monitor loop (LIVE TELEMETRY + RCA)")
    
    asyncio.create_task(asyncio.to_thread(run_monitor_loop))

    yield

    log("API shutdown: application stopping")


# -------------------------------------------------
# FastAPI App
# -------------------------------------------------

app = FastAPI(
    title="ETW GenAI Kernel Monitor API",
    description="Live CPU/RAM Telemetry + Spike Detection + RCA",
    lifespan=lifespan,
)

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------
# SPIKE / RCA ROUTES
# -------------------------------------------------

@app.get("/api/spikes")
def get_spikes():
    """Returns all detected spikes (newest first)."""
    return {"spikes": STATE.get_spikes()}


@app.get("/api/latest-rca")
def get_latest_rca():
    """Returns the RCA attached to the most recent spike."""
    return {"latest_rca": STATE.get_latest_rca()}


@app.get("/api/spikes/{spike_id}")
def get_spike(spike_id: int):
    """Returns a specific spike by ID."""

    spike = STATE.get_spike(spike_id)

    if not spike:
        raise HTTPException(
            status_code=404,
            detail=f"Spike with id={spike_id} not found",
        )

    return spike


# -------------------------------------------------
# ✅ LIVE TELEMETRY ROUTES (NEW)
# -------------------------------------------------

@app.get("/api/telemetry/latest")
def telemetry_latest():
    """
    Very fast endpoint returning the latest CPU/RAM sample.
    Ideal for indicators or low-latency polling.
    """
    sample = STATE.get_latest_telemetry()

    return {
        "telemetry": sample
    }


@app.get("/api/telemetry/window")
def telemetry_window(
    seconds: int = Query(
        60,
        ge=1,
        le=600,
        description="Return telemetry samples from the last N seconds (max 600).",
    )
):
    """
    Returns a rolling window of telemetry samples for graphing.
    """
    samples = STATE.get_telemetry_window(seconds)

    return {
        "window_seconds": seconds,
        "samples": samples,
    }
