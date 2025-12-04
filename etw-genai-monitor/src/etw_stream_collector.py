import os
import json
import psutil
import subprocess
import threading
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from .utils.logger import log

# ------------------------------------------
# Configuration
# ------------------------------------------

RETENTION_SECONDS = 100

MAX_EVENTS = 10000
MAX_EVENTS_PER_PID = 2000

ETW_EXE_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "windows",
    "EtwKernelTracer",
    "bin",
    "Release",
    "net8.0",
    "EtwKernelTracer.exe",
)

# ------------------------------------------
# ETW STREAM COLLECTOR
# ------------------------------------------

class EtwStreamCollector:
    """
    Production-grade ETW stream collector.

    Capabilities:
    ---------------------
    ✅ Rolling event buffer (global + per PID)
    ✅ Safe timestamp normalization
    ✅ Schema hardening
    ✅ Tracer crash detection + logging
    ✅ Non-blocking stderr drain
    ✅ Retention purging
    ✅ Built-in RCA utilities
    """

    def __init__(self, etw_exe_path: str = None):

        self.etw_exe_path = etw_exe_path or ETW_EXE_DEFAULT

        self.events = deque(maxlen=MAX_EVENTS)
        self.events_by_pid = defaultdict(lambda: deque(maxlen=MAX_EVENTS_PER_PID))

        self.proc: subprocess.Popen | None = None
        self._stop_flag = False

        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

        if not os.path.exists(self.etw_exe_path):
            raise FileNotFoundError(
                f"ETW tracer exe not found at: {self.etw_exe_path}"
            )

        self._start_tracer()

    # ------------------------------------------

    def _start_tracer(self):
        log(f"Starting ETW tracer: {self.etw_exe_path}")

        try:
            self.proc = subprocess.Popen(
                [self.etw_exe_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to start tracer: {e}")

        # Stdout reader
        self._reader_thread = threading.Thread(
            target=self._stdout_reader_loop,
            daemon=True,
        )
        self._reader_thread.start()

        # Stderr drain (prevents buffer deadlock + error visibility)
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader_loop,
            daemon=True,
        )
        self._stderr_thread.start()

    # ------------------------------------------

    def _stderr_reader_loop(self):
        """Drain stderr so subprocess never blocks."""
        if not self.proc or not self.proc.stderr:
            return

        for line in self.proc.stderr:
            if self._stop_flag:
                break

            if line.strip():
                log(f"[ETW STDERR] {line.strip()}")

    # ------------------------------------------

    def _stdout_reader_loop(self):

        if not self.proc or not self.proc.stdout:
            return

        for line in self.proc.stdout:

            if self._stop_flag:
                break

            line = line.strip()
            if not line:
                continue

            try:
                ev = json.loads(line)
            except Exception:
                log("Invalid JSON from ETW; line skipped")
                continue

            # --------------------------------------
            # Timestamp normalization
            # --------------------------------------
            try:
                ev_ts = ev.get("ts")
                ev["ts"] = datetime.fromisoformat(ev_ts).astimezone(timezone.utc)
            except Exception:
                ev["ts"] = datetime.now(timezone.utc)

            # --------------------------------------
            # Schema hardening
            # --------------------------------------
            ev.setdefault("pid", None)
            ev.setdefault("tid", None)
            ev.setdefault("provider", "unknown")
            ev.setdefault("event_type", "unknown")
            ev.setdefault("event_name", "")
            ev.setdefault("task", "")
            ev.setdefault("payload", {})

            if not isinstance(ev["payload"], dict):
                ev["payload"] = {}

            # --------------------------------------
            # Append to buffers
            # --------------------------------------
            self.events.append(ev)

            pid = ev.get("pid")
            if pid is not None:
                self.events_by_pid[pid].append(ev)

            # --------------------------------------
            # Purge old data
            # --------------------------------------
            self._purge_old_events()

    # ------------------------------------------

    def _purge_old_events(self):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=RETENTION_SECONDS)

        # Global queue
        while self.events and self.events[0]["ts"] < cutoff:
            old = self.events.popleft()

            pid = old.get("pid")
            if pid in self.events_by_pid:
                dq = self.events_by_pid[pid]
                if dq and dq[0] is old:
                    dq.popleft()
                if not dq:
                    del self.events_by_pid[pid]

    # ------------------------------------------

    def stop(self):
        log("Stopping ETW tracer")

        self._stop_flag = True

        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

    # ------------------------------------------
    # ✅ PUBLIC QUERY APIS
    # ------------------------------------------

    def get_recent_events(self, limit: int = 300) -> List[Dict[str, Any]]:
        return list(self.events)[-limit:]

    def get_events_by_pid(self, pid: int, limit: int = 500):
        return list(self.events_by_pid.get(pid, []))[-limit:]

    # ------------------------------------------
    # RCA / HEURISTICS
    # ------------------------------------------

    def detect_gc_events(self):
        return [
            ev for ev in self.events
            if ev.get("provider") == "Microsoft-Windows-DotNETRuntime"
            and "GC" in str(ev.get("event_name"))
        ]

    def detect_page_faults(self):
        return [
            ev for ev in self.events
            if ev.get("task") == "Memory"
        ]

    def detect_cpu_contention(self):
        switch_count = sum(
            1 for ev in self.events
            if ev.get("event_type") == "context_switch"
        )

        return {
            "context_switch_rate": round(switch_count / max(1, RETENTION_SECONDS), 2),
            "burst_detected": switch_count > 1000,
        }

    def aggregate_network_usage(self):
        usage = defaultdict(int)

        for ev in self.events:
            size = ev.get("net_bytes") or 0
            pid = ev.get("pid")

            if size and pid is not None:
                usage[pid] += size

        return dict(sorted(usage.items(), key=lambda x: x[1], reverse=True))

    def aggregate_disk_usage(self):
        usage = defaultdict(int)

        for ev in self.events:
            size = ev.get("disk_bytes") or 0
            pid = ev.get("pid")

            if size and pid is not None:
                usage[pid] += size

        return dict(sorted(usage.items(), key=lambda x: x[1], reverse=True))

    def detect_thread_spikes(self):
        counts = defaultdict(int)

        for ev in self.events:
            if ev.get("event_type") == "thread_start":
                counts[ev.get("pid")] += 1

        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------
    # OS PROCESS SNAPSHOT
    # ------------------------------------------

    def current_top_processes(self, top_n: int = 20):

        snapshot = []

        for p in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "cmdline"]
        ):

            try:
                info = p.info

                snapshot.append({
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "cpu_percent": info.get("cpu_percent"),
                    "mem_percent": info.get("memory_percent"),
                    "cmdline": " ".join(info.get("cmdline") or []),
                })

            except Exception:
                continue

        snapshot.sort(
            key=lambda x: x.get("cpu_percent") or 0,
            reverse=True
        )

        return snapshot[:top_n]
