import numpy as np
import psutil
from collections import defaultdict
from statistics import median


# -------------------------
# Helpers
# -------------------------

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def _robust_z_score(val, med, mad):
    mad = max(mad, 0.01)
    return abs(val - med) / mad


def _cosine_similarity(a, b):
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _mahalanobis_scores(matrix):
    """
    Robust-ish Mahalanobis distance using median center and
    pseudo-inverse covariance. Returns a 1D array of distances.
    """
    X = np.asarray(matrix, dtype=float)
    if X.shape[0] < 2:
        # Not enough samples to define covariance
        return np.zeros(X.shape[0], dtype=float)

    # Robust center: median per feature
    center = np.median(X, axis=0)
    Xc = X - center

    # Covariance (add small ridge on diag for stability)
    cov = np.cov(Xc, rowvar=False)
    if cov.ndim == 0:
        cov = np.array([[cov]])
    dim = cov.shape[0]
    cov += np.eye(dim) * 1e-6

    cov_inv = np.linalg.pinv(cov)

    dists = []
    for row in Xc:
        row = row.reshape(1, -1)
        m2 = float(row @ cov_inv @ row.T)
        m2 = max(m2, 0.0)
        dists.append(np.sqrt(m2))
    return np.array(dists, dtype=float)


def _lead_lag_score(global_series, pid_series, max_lag=5):
    """
    Cross-correlation based lead/lag score in [0,1].
    Positive score is higher when:
      - correlation is strong
      - PID tends to lead (negative lag).
    If series are missing/too short, returns 0.
    """
    if global_series is None or pid_series is None:
        return 0.0

    g = np.asarray(global_series, dtype=float)
    p = np.asarray(pid_series, dtype=float)

    n = min(len(g), len(p))
    if n < 4:
        return 0.0

    g = g[:n]
    p = p[:n]

    g = g - g.mean()
    p = p - p.mean()

    g_norm = np.linalg.norm(g)
    p_norm = np.linalg.norm(p)
    if g_norm == 0 or p_norm == 0:
        return 0.0

    best_corr = 0.0
    best_lag = 0

    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            # PID leads (pid earlier)
            g_seg = g[-lag:]
            p_seg = p[:n + lag]
        elif lag > 0:
            # PID lags
            g_seg = g[:n - lag]
            p_seg = p[lag:]
        else:
            g_seg = g
            p_seg = p

        if len(g_seg) < 3:
            continue

        num = float(np.dot(g_seg, p_seg))
        den = np.linalg.norm(g_seg) * np.linalg.norm(p_seg)
        if den == 0:
            continue

        corr = num / den  # in [-1,1]
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_corr <= 0:
        return 0.0

    # Prefer negative lag (PID leads), neutral at 0, penalize lagging
    if best_lag < 0:
        lag_factor = 1.0
    elif best_lag == 0:
        lag_factor = 0.8
    else:
        lag_factor = 0.5

    score = best_corr * lag_factor
    # Clamp to [0,1]
    return max(0.0, min(1.0, score))


# -------------------------
# PID Ranker (v2)
# -------------------------

class PidStatisticalRanker:
    """
    RCA-focused PID ranker using:

    ANOMALY (multivariate):
        - RAM %
        - ETW event counts (event_rate, thread_rate, cpu_samples)
        - Page fault count
        - GC event count
        - Network bytes (log)
        - Disk bytes (log)
        - CPU % (Mahalanobis only)

    ENERGY CONTRIBUTION:
        - PID CPU% vs global spike CPU
        - PID RAM% vs spike RAM
        - PID Disk bytes vs total disk bytes
        - PID Net bytes vs total net bytes

    CORRELATION:
        - PID resource vector vs global spike vector (cosine)
        - (Optional) time-series spike lead/lag vs global CPU

    FINAL SCORE:
        - Normalized blend of:
            - multivariate anomaly (z-score + Mahalanobis)
            - energy contribution
            - correlation (cosine + lead/lag)
    """

    def __init__(self):
        # Weights among the three main components (sum ~= 1.0)
        self.weight_anomaly = 0.4
        self.weight_energy = 0.4
        self.weight_correlation = 0.2

    # ----------------------------------------------------

    def rank_pids(
        self,
        etw_events,
        spike_cpu,
        spike_ram,
        global_cpu_series=None,
        pid_cpu_series=None,
    ):
        """
        etw_events: iterable of event dicts; must contain "pid".
        spike_cpu, spike_ram: global spike CPU/RAM percentages.
        global_cpu_series: optional list/array of global CPU over time.
        pid_cpu_series: optional dict[pid] -> list/array of CPU over time.
        """

        buckets = defaultdict(list)
        for ev in etw_events:
            pid = ev.get("pid")
            if pid is not None:
                buckets[pid].append(ev)

        if not buckets:
            return []

        pid_rows = []

        total_disk_bytes = 0.0
        total_net_bytes = 0.0

        for pid, events in buckets.items():
            try:
                proc = psutil.Process(pid)

                name = proc.name()
                cmdline = " ".join(proc.cmdline())

                # per-process CPU and RAM usage
                cpu_pct = proc.cpu_percent(interval=0.05)
                ram_pct = proc.memory_percent()

            except Exception:
                name = "Unknown"
                cmdline = ""
                cpu_pct = 0.0
                ram_pct = 0.0

            # ----------------------------------------------------
            # ETW-derived rates / counts
            # ----------------------------------------------------

            event_rate = len(events)

            thread_rate = sum(
                1 for e in events
                if "thread" in str(e.get("event_type", "")).lower()
            )

            cpu_samples = sum(
                1 for e in events
                if "Profile" in str(e.get("task", ""))
            )

            page_faults = sum(
                1 for e in events
                if e.get("task") == "Memory"
            )

            gc_events = sum(
                1 for e in events
                if "GC" in str(e.get("event_name", ""))
            )

            net_bytes = sum(_safe_float(e.get("net_bytes")) for e in events)
            disk_bytes = sum(_safe_float(e.get("disk_bytes")) for e in events)

            total_disk_bytes += disk_bytes
            total_net_bytes += net_bytes

            pid_rows.append({
                "pid": pid,
                "name": name,
                "cmdline": cmdline,

                "cpu_pct": round(cpu_pct, 2),
                "ram_pct": round(ram_pct, 2),

                "event_rate": event_rate,
                "thread_rate": thread_rate,
                "cpu_samples": cpu_samples,
                "page_faults": page_faults,
                "gc_events": gc_events,

                "net_bytes": round(net_bytes, 2),
                "disk_bytes": round(disk_bytes, 2),
            })

        if not pid_rows:
            return []

        # ----------------------------------------------------
        # Feature shaping (log for bytes)
        # ----------------------------------------------------
        for p in pid_rows:
            p["net_bytes_log"] = np.log1p(_safe_float(p["net_bytes"]))
            p["disk_bytes_log"] = np.log1p(_safe_float(p["disk_bytes"]))

        # ----------------------------------------------------
        # Z-score anomaly baselines (robust)
        # ----------------------------------------------------
        anomaly_feats_z = [
            "ram_pct",
            "event_rate",
            "thread_rate",
            "cpu_samples",
            "page_faults",
            "gc_events",
            "net_bytes_log",
            "disk_bytes_log",
        ]

        stats = {}
        for feat in anomaly_feats_z:
            vals = [_safe_float(p[feat]) for p in pid_rows]
            med = median(vals)
            mad = median(abs(v - med) for v in vals)
            stats[feat] = (med, mad)

        z_anomaly_raws = []
        for p in pid_rows:
            z_vals = []
            for feat in anomaly_feats_z:
                val = _safe_float(p[feat])
                med, mad = stats[feat]
                z_vals.append(_robust_z_score(val, med, mad))
            z_anom = sum(z_vals) / len(z_vals)
            p["z_anomaly"] = z_anom
            z_anomaly_raws.append(z_anom)

        # ----------------------------------------------------
        # Mahalanobis anomaly (multivariate)
        # ----------------------------------------------------
        mahal_feats = [
            "cpu_pct",
            "ram_pct",
            "event_rate",
            "thread_rate",
            "cpu_samples",
            "page_faults",
            "gc_events",
            "net_bytes_log",
            "disk_bytes_log",
        ]

        X = np.array([
            [_safe_float(p[f]) for f in mahal_feats]
            for p in pid_rows
        ], dtype=float)

        mahal_raws = _mahalanobis_scores(X)
        for p, m in zip(pid_rows, mahal_raws):
            p["mahalanobis"] = float(m)

        # ----------------------------------------------------
        # Energy contribution scores
        # ----------------------------------------------------
        energy_raws = []

        denom_cpu = max(spike_cpu, 1.0)
        denom_ram = max(spike_ram, 1.0)
        denom_disk = max(total_disk_bytes, 1.0)
        denom_net = max(total_net_bytes, 1.0)

        for p in pid_rows:
            cpu_contrib = _safe_float(p["cpu_pct"]) / denom_cpu
            ram_contrib = _safe_float(p["ram_pct"]) / denom_ram
            disk_contrib = _safe_float(p["disk_bytes"]) / denom_disk
            net_contrib = _safe_float(p["net_bytes"]) / denom_net

            # Clip to non-negative; we don't mind >1 a bit, will normalize
            cpu_contrib = max(cpu_contrib, 0.0)
            ram_contrib = max(ram_contrib, 0.0)
            disk_contrib = max(disk_contrib, 0.0)
            net_contrib = max(net_contrib, 0.0)

            energy_raw = (
                0.4 * cpu_contrib +
                0.3 * ram_contrib +
                0.15 * disk_contrib +
                0.15 * net_contrib
            )
            p["energy_raw"] = energy_raw
            energy_raws.append(energy_raw)

        # ----------------------------------------------------
        # Correlation: cosine + optional lead/lag
        # ----------------------------------------------------
        corr_raws = []

        for p in pid_rows:
            pid_vec = [
                _safe_float(p["cpu_pct"]),
                _safe_float(p["ram_pct"]),
                _safe_float(p["event_rate"]),
                _safe_float(p["thread_rate"]),
                _safe_float(p["cpu_samples"]),
                _safe_float(p["page_faults"]),
                _safe_float(p["gc_events"]),
                _safe_float(p["net_bytes_log"]),
                _safe_float(p["disk_bytes_log"]),
            ]

            spike_vec = [
                spike_cpu,
                spike_ram,
                1, 1, 1, 1, 1, 1, 1,
            ]

            cos_corr = _cosine_similarity(pid_vec, spike_vec)

            if pid_cpu_series is not None:
                series = pid_cpu_series.get(p["pid"])
            else:
                series = None

            lead_score = _lead_lag_score(global_cpu_series, series)

            corr_raw = 0.7 * cos_corr + 0.3 * lead_score
            p["cosine_correlation"] = cos_corr
            p["lead_lag_score"] = lead_score
            p["correlation_raw"] = corr_raw

            corr_raws.append(corr_raw)

        # ----------------------------------------------------
        # Normalize component scores into [0,1]
        # ----------------------------------------------------
        def _normalize_list(vals):

            arr = np.asarray(list(vals), dtype=float).ravel()

            # Safe empty check
            if arr.size == 0:
                return [0.0]

            max_v = float(np.max(arr))

            if max_v <= 0:
                return [0.0 for _ in arr]

            return [float(v / max_v) for v in arr]


        z_norms = _normalize_list(z_anomaly_raws)
        mahal_norms = _normalize_list(mahal_raws)
        energy_norms = _normalize_list(energy_raws)
        corr_norms = _normalize_list(corr_raws)

        # Combined anomaly = blend of z + Mahalanobis
        anomaly_norms = [
            0.5 * z_n + 0.5 * m_n
            for z_n, m_n in zip(z_norms, mahal_norms)
        ]

        severity_boost = 1.25 if spike_cpu > 85 or spike_ram > 80 else 1.0

        final_raws = []
        for p, an, en, cn in zip(pid_rows, anomaly_norms, energy_norms, corr_norms):
            final_raw = severity_boost * (
                self.weight_anomaly * an +
                self.weight_energy * en +
                self.weight_correlation * cn
            )

            p["anomaly_score"] = round(an, 4)
            p["energy_score"] = round(en, 4)
            p["correlation_score"] = round(cn, 4)

            final_raws.append(final_raw)

        max_final = max(final_raws) if final_raws else 1.0
        if max_final <= 0:
            max_final = 1.0

        ranked = []
        for p, raw in zip(pid_rows, final_raws):
            p["final_score"] = round(min(1.0, raw / max_final), 4)
            ranked.append(p)

        ranked.sort(key=lambda x: x["final_score"], reverse=True)
        return ranked[:15]
