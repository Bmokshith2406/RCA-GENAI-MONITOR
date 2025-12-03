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
# ETW Stream Collector
# ------------------------------------------

class EtwStreamCollector:
    """
    Starts the C# ETW tracer and consumes JSON events from stdout.
    Maintains:
      - Rolling event window
      - PID-indexed event lists (for RCA lookups)
      - Lightweight metric snapshots for fast analysis
    """

    def __init__(self, etw_exe_path: str = None, max_events: int = MAX_EVENTS):

        self.etw_exe_path = etw_exe_path or ETW_EXE_DEFAULT

        self.events = deque(maxlen=max_events)
        self.events_by_pid = defaultdict(deque)

        self.proc: subprocess.Popen | None = None
        self._stop_flag = False
        self._thread: threading.Thread | None = None

        if not os.path.exists(self.etw_exe_path):
            raise FileNotFoundError(
                f"ETW tracer exe not found at: {self.etw_exe_path}"
            )

        self._start_tracer()

    # ------------------------------------------

    def _start_tracer(self):
        log(f"Starting ETW tracer: {self.etw_exe_path}")

        self.proc = subprocess.Popen(
            [self.etw_exe_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True
        )
        self._thread.start()

    # ------------------------------------------

    def _reader_loop(self):

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
                continue

            # --------------------------------------------------
            # ✅ Normalize timestamp
            # --------------------------------------------------
            try:
                ev["ts"] = datetime.fromisoformat(ev.get("ts")).astimezone(timezone.utc)
            except Exception:
                ev["ts"] = datetime.now(timezone.utc)

            # --------------------------------------------------
            # ✅ Ensure payload is valid dict
            # --------------------------------------------------
            payload = ev.get("payload")
            if not isinstance(payload, dict):
                ev["payload"] = {}

            # --------------------------------------------------
            # ✅ Append
            # --------------------------------------------------
            self.events.append(ev)

            pid = ev.get("pid")

            if pid is not None:
                self.events_by_pid[pid].append(ev)

            # --------------------------------------------------
            # ✅ Purge old events
            # --------------------------------------------------
            self._purge_old_events()

    # ------------------------------------------

    def _purge_old_events(self):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=RETENTION_SECONDS)

        while self.events:
            if self.events[0]["ts"] >= cutoff:
                break

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

        self._stop_flag = True

        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    # ------------------------------------------

    # ✅ PUBLIC QUERY APIS

    def get_recent_events(self, limit: int = 300) -> List[Dict[str, Any]]:
        return list(self.events)[-limit:]

    # ------------------------------------------

    def get_events_by_pid(self, pid: int, limit: int = 500):
        return list(self.events_by_pid.get(pid, []))[-limit:]

    # ------------------------------------------

    def detect_gc_events(self):
        """Find managed GC burst events"""
        return [
            ev for ev in self.events
            if ev.get("provider") == "Microsoft-Windows-DotNETRuntime"
            and "GC" in str(ev.get("event_name"))
        ]

    # ------------------------------------------

    def detect_page_faults(self):
        """Detect page fault bursts"""
        return [
            ev for ev in self.events
            if ev.get("task") == "Memory"
        ]

    # ------------------------------------------

    def detect_cpu_contention(self):
        """
        Detect high CPU contention.
        Signal: many context-switch events concentrated in a short window.
        """
        switch_count = sum(
            1 for ev in self.events
            if ev.get("event_type") == "context_switch"
        )

        return {
            "context_switch_rate": round(switch_count / max(1, RETENTION_SECONDS), 2),
            "burst_detected": switch_count > 1000
        }

    # ------------------------------------------

    def aggregate_network_usage(self):
        usage = defaultdict(int)

        for ev in self.events:
            size = ev.get("net_bytes") or 0
            pid = ev.get("pid")

            if size and pid is not None:
                usage[pid] += size

        return dict(sorted(usage.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------

    def aggregate_disk_usage(self):
        usage = defaultdict(int)

        for ev in self.events:
            size = ev.get("disk_bytes") or 0
            pid = ev.get("pid")

            if size and pid is not None:
                usage[pid] += size

        return dict(sorted(usage.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------

    def detect_thread_spikes(self):
        counts = defaultdict(int)

        for ev in self.events:
            if ev.get("event_type") == "thread_start":
                counts[ev.get("pid")] += 1

        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------

    def current_top_processes(self, top_n: int = 20):
        """
        Return snapshot of live processes from OS side
        """
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
            key=lambda x: x["cpu_percent"] or 0,
            reverse=True
        )

        return snapshot[:top_n]
