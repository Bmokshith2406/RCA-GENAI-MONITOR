from dataclasses import dataclass, asdict
from threading import Lock
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

# ------------------------------------------
# CONFIG
# ------------------------------------------

# ------------------------------------------
# Utilities
# ------------------------------------------

def iso_now():
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

    # ✅ NEW metadata
    spike_type: str = "unknown"
    severity_score: float = 0.0

    attached_event_count: int = 0

    rca: Dict | None = None
    etw_events: List[Dict[str, Any]] | None = None


# ------------------------------------------
# Global Monitor State
# ------------------------------------------

class MonitorState:

    def __init__(self):
        self._events: List[Dict[str, Any]] = []
        self._spikes: List[SpikeRecord] = []
        self._next_spike_id: int = 1
        self.lock = Lock()

    # ----------------------------------
    # EVENT STORAGE
    # ----------------------------------

    def append_event(self, event: Dict[str, Any]):

        if "ts" not in event:
            event["ts"] = iso_now()

        with self.lock:
            self._events.append(event)


    def get_events(self, limit: int = 200):

        with self.lock:
            return list(self._events)[-limit:]

    # ----------------------------------
    # SPIKE STORAGE
    # ----------------------------------

    def add_spike(self, info: Dict[str, Any]) -> SpikeRecord:

        with self.lock:

            spike = SpikeRecord(
                id=self._next_spike_id,
                detected_at=iso_now(),
                start_time=info["start_time"],
                confirm_time=info["confirm_time"],
                cpu_at_confirm=info["cpu_at_confirm"],
                ram_at_confirm=info["ram_at_confirm"],
                reason=info.get("reason", "threshold exceeded"),

                spike_type=info.get("spike_type", "unknown"),
                severity_score=info.get("severity_score", 0.0),
            )

            self._spikes.append(spike)
            self._next_spike_id += 1

            return spike

    def attach_events(self, spike_id: int, events: List[Dict[str, Any]]):

        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:

                    # ✅ Protect memory size
                    s.attached_event_count = len(events)
                    s.etw_events = events[-500:]

                    break

    def attach_rca(self, spike_id: int, rca: Dict):

        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:
                    s.rca = rca
                    break

    # ----------------------------------
    # READ APIS
    # ----------------------------------

    def get_spikes(self):

        with self.lock:
            return [asdict(s) for s in reversed(self._spikes)]

    def get_spike(self, spike_id: int):

        with self.lock:
            for s in self._spikes:
                if s.id == spike_id:
                    return asdict(s)

        return None

    def get_latest_rca(self):

        with self.lock:
            for s in reversed(self._spikes):
                if s.rca:
                    return s.rca

        return None


# ------------------------------------------
# Singleton
# ------------------------------------------

STATE = MonitorState()
