from dataclasses import dataclass, asdict
from threading import Lock
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from collections import deque

# ------------------------------------------
# CONFIG
# ------------------------------------------

MAX_SPIKES_HISTORY = 2000
MAX_ATTACHED_EVENTS = 500

# ✅ NEW — telemetry history (seconds)
MAX_TELEMETRY_BUFFER = 300   # 5 minutes @ 1 Hz

# ------------------------------------------
# Utilities
# ------------------------------------------

def iso_now() -> str:
    """Returns the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------
# Data Models
# ------------------------------------------

@dataclass
class SpikeRecord:
    id: int
    detected_at: str
    start_time: str
    confirm_time: str
    cpu_at_confirm: float
    ram_at_confirm: float
    reason: str

    spike_type: str = "unknown"
    severity_score: float = 0.0

    attached_event_count: int = 0

    # RCA & related ETW snapshot
    rca: Dict | None = None
    etw_events: List[Dict[str, Any]] | None = None


# ------------------------------------------
# Global Monitor State
# ------------------------------------------

class MonitorState:

    def __init__(self):
        # --------------------------
        # Spikes
        # --------------------------
        self._spikes: deque[SpikeRecord] = deque(maxlen=MAX_SPIKES_HISTORY)
        self._next_spike_id: int = 1

        # --------------------------
        # ✅ LIVE TELEMETRY BUFFER
        # --------------------------
        self._telemetry: deque[Dict[str, Any]] = deque(maxlen=MAX_TELEMETRY_BUFFER)

        self.lock = Lock()

    # ----------------------------------
    # TELEMETRY STORAGE (NEW)
    # ----------------------------------

    def add_telemetry(self, cpu: float, ram: float):
        """
        Append a telemetry sample to the rolling history buffer.
        """
        sample = {
            "ts": iso_now(),
            "cpu": float(cpu),
            "ram": float(ram),
        }

        with self.lock:
            self._telemetry.append(sample)

    def get_latest_telemetry(self) -> Dict[str, Any] | None:
        """
        Returns the most recent telemetry sample.
        """
        with self.lock:
            if not self._telemetry:
                return None

            return dict(self._telemetry[-1])

    def get_telemetry_window(self, seconds: int) -> List[Dict[str, Any]]:
        """
        Return telemetry samples within the last N seconds.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)

        samples = []

        with self.lock:
            for item in reversed(self._telemetry):
                ts = datetime.fromisoformat(item["ts"])

                if ts < cutoff:
                    break

                samples.insert(0, dict(item))

        return samples

    # ----------------------------------
    # SPIKE STORAGE
    # ----------------------------------

    def add_spike(self, info: Dict[str, Any]) -> SpikeRecord:
        """Insert a new spike entry."""
        with self.lock:
            spike = SpikeRecord(
                id=self._next_spike_id,
                detected_at=iso_now(),

                start_time=str(info.get("start_time", iso_now())),
                confirm_time=str(info.get("confirm_time", iso_now())),

                cpu_at_confirm=float(info.get("cpu_at_confirm", 0.0)),
                ram_at_confirm=float(info.get("ram_at_confirm", 0.0)),

                reason=str(info.get("reason", "threshold exceeded")),

                spike_type=str(info.get("spike_type", "unknown")),
                severity_score=float(info.get("severity_score", 0.0)),
            )

            self._spikes.append(spike)
            self._next_spike_id += 1

            return spike

    # ----------------------------------
    # RCA & EVENT ATTACHMENT
    # ----------------------------------

    def attach_events(self, spike_id: int, events: List[Dict[str, Any]]):
        if not isinstance(events, list):
            return

        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:
                    limited = events[-MAX_ATTACHED_EVENTS:]
                    s.attached_event_count = len(events)
                    s.etw_events = limited
                    break

    def attach_rca(self, spike_id: int, rca: Dict):
        if not isinstance(rca, dict):
            return

        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:
                    s.rca = dict(rca)
                    break

    # ----------------------------------
    # READ APIS
    # ----------------------------------

    def get_spikes(self):
        """Returns all spike records as dictionaries, newest first."""
        with self.lock:
            return [asdict(s) for s in reversed(self._spikes)]

    def get_spike(self, spike_id: int):
        """Returns a single spike record by ID."""
        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:
                    return asdict(s)

        return None

    def get_latest_rca(self):
        """Returns the RCA from the newest spike that has one."""
        with self.lock:
            for s in reversed(self._spikes):
                if s.rca:
                    return dict(s.rca)

        return None


# ------------------------------------------
# Singleton
# ------------------------------------------

STATE = MonitorState()
