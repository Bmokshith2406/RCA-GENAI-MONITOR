import time
import psutil

from .utils.logger import log
from .spike_detector import SpikeDetector
from .etw_stream_collector import EtwStreamCollector
from .gemini_client.gemini_client import analyze_root_cause
from .state import STATE, iso_now
from .pid_ranker import PidStatisticalRanker


# ------------------------------------------------
# Create ranker ONCE
# ------------------------------------------------
ranker = PidStatisticalRanker()


# ------------------------------------------------
# ✅ ULTRA-SAFE CASTERS (NO CRASH POSSIBLE)
# ------------------------------------------------

def _safe_dict(x):
    """
    Hard guarantee: ALWAYS returns a dict.
    Never attempts dict(x) which crashes on float/int.
    """
    return x if isinstance(x, dict) else {}


def _safe_list(x):
    """
    Hard guarantee: ALWAYS returns a list.
    Prevents len() crashes if float/None/etc.
    """
    if isinstance(x, list):
        return x
    if isinstance(x, (tuple, set)):
        return list(x)
    return []


# ------------------------------------------------
# MONITOR LOOP
# ------------------------------------------------

def run_monitor_loop():

    log("Starting ETW GenAI monitor loop (LIVE TELEMETRY + RCA MODE)")

    # ------------------------------------------------
    # Start ETW kernel tracer
    # ------------------------------------------------
    try:
        etw = EtwStreamCollector()
    except Exception as e:
        log(f"❌ Failed to start ETW tracer: {e}")
        return

    # ------------------------------------------------
    # Spike detector
    # ------------------------------------------------
    detector = SpikeDetector(
        baseline_window=300,
        sample_interval=1.0,
        z_score=2.5,
        derivative_threshold=5.0,
        derivative_len=3,
        confirm_seconds=20,
        cpu_threshold=75.0,
        ram_threshold=80.0,
    )

    try:
        while True:

            # ------------------------------------------------
            # ✅ SAFE RESOURCE SAMPLING
            # ------------------------------------------------
            try:
                cpu = psutil.cpu_percent(interval=None)
            except Exception:
                cpu = 0.0

            try:
                ram = psutil.virtual_memory().percent
            except Exception:
                ram = 0.0

            # ------------------------------------------------
            # ✅ CONTINUOUS TELEMETRY FEED (NEW)
            # ------------------------------------------------
            STATE.add_telemetry(cpu, ram)

            detector.add_sample({
                "ts": iso_now(),
                "cpu": cpu,
                "ram": ram,
            })

            # ------------------------------------------------
            # SPIKE DETECTION
            # ------------------------------------------------
            triggered, info = detector.check()

            if not triggered:
                time.sleep(1.0)
                continue

            # ------------------------------------------------
            # 🔥 SPIKE TRIGGERED
            # ------------------------------------------------
            log(
                f"🔥 Spike detected: "
                f"start={info['start_time']} "
                f"confirm={info['confirm_time']} "
                f"CPU={info['cpu_at_confirm']} "
                f"RAM={info['ram_at_confirm']}"
            )

            spike_record = STATE.add_spike(info)

            # ------------------------------------------------
            # 📦 FORENSIC ETW SNAPSHOT
            # ------------------------------------------------
            try:
                spike_events = etw.get_recent_events(limit=1500) or []
            except Exception as e:
                log(f"⚠ ETW snapshot failed: {e}")
                spike_events = []

            STATE.attach_events(spike_record.id, spike_events)

            # ------------------------------------------------
            # 📊 STATISTICAL PID RANKING
            # ------------------------------------------------
            try:
                ranked_candidates = ranker.rank_pids(
                    etw_events=spike_events,
                    spike_cpu=info["cpu_at_confirm"],
                    spike_ram=info["ram_at_confirm"],
                )
            except Exception as e:
                log(f"⚠ PID ranking failed: {e}")
                ranked_candidates = []

            # ------------------------------------------------
            # SAFE TELEMETRY EXTRACTION
            # ------------------------------------------------
            try:
                cpu_stats     = _safe_dict(etw.detect_cpu_contention())
                net_usage     = _safe_dict(etw.aggregate_network_usage())
                disk_usage    = _safe_dict(etw.aggregate_disk_usage())
                thread_spikes = _safe_dict(etw.detect_thread_spikes())
            except Exception as e:
                log(f"⚠ Telemetry aggregation failed: {e}")

                cpu_stats = {}
                net_usage = {}
                disk_usage = {}
                thread_spikes = {}

            try:
                gc_events   = _safe_list(etw.detect_gc_events())
                page_faults = _safe_list(etw.detect_page_faults())
            except Exception:
                gc_events = []
                page_faults = []

            # ------------------------------------------------
            # 🧠 RCA EVIDENCE ASSEMBLY
            # ------------------------------------------------
            evidence = {
                "collected_at": iso_now(),

                "cpu_at_confirm": info["cpu_at_confirm"],
                "ram_at_confirm": info["ram_at_confirm"],

                "spike_info": info,
                "ranked_pid_candidates": ranked_candidates,

                "cpu_contention": cpu_stats,
                "network_usage_top_pids": dict(list(net_usage.items())[:10]),
                "disk_usage_top_pids": dict(list(disk_usage.items())[:10]),
                "thread_spikes": dict(list(thread_spikes.items())[:10]),

                "gc_event_count": len(gc_events),
                "page_fault_event_count": len(page_faults),
                "etw_events_count": len(spike_events),
            }

            # ------------------------------------------------
            # 🤖 GEMINI RCA INVOCATION
            # ------------------------------------------------
            try:
                log("🤖 Sending enriched RCA evidence to Gemini...")
                rca = analyze_root_cause(evidence)
                log("📨 Gemini RCA result received")

                STATE.attach_rca(spike_record.id, rca)
                log(f"✅ RCA attached to spike #{spike_record.id}")

            except Exception as e:
                log(f"❌ Gemini RCA FAILED — continuing loop: {e}")

            time.sleep(1.0)

    except Exception as e:
        log(f"❌ Monitor loop crashed: {e}")

    finally:
        try:
            etw.stop()
        except Exception:
            pass

        log("Monitor loop terminated")
