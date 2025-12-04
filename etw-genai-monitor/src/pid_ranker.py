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

    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)

    if na == 0 or nb == 0:
        return 0.0

    return float(np.dot(a, b) / (na * nb))


def _mahalanobis_scores(matrix):
    """
    Robust Mahalanobis distance:
      - Median-based center
      - Pseudo-inverse covariance
      - Diagonal ridge stabilizer (1e-3)
    """
    X = np.asarray(matrix, dtype=float)

    if X.shape[0] < 2:
        return np.zeros(X.shape[0], dtype=float)

    center = np.median(X, axis=0)
    Xc = X - center

    cov = np.cov(Xc, rowvar=False)

    if cov.ndim == 0:
        cov = np.array([[cov]])

    dim = cov.shape[0]

    # ✅ stronger stabilization for real-world skew
    cov += np.eye(dim) * 1e-3

    cov_inv = np.linalg.pinv(cov)

    dists = []
    for row in Xc:
        row = row.reshape(1, -1)
        dist = float(row @ cov_inv @ row.T)
        dists.append(np.sqrt(max(dist, 0.0)))

    return np.array(dists, dtype=float)


def _lead_lag_score(global_series, pid_series, max_lag=5):
    """
    Cross-correlation based causality metric in [0,1].
    - Rewards correlation strength
    - Rewards PID leading the spike
    """
    if global_series is None or pid_series is None:
        return 0.0

    g = np.asarray(global_series, dtype=float)
    p = np.asarray(pid_series, dtype=float)

    n = min(len(g), len(p))
    if n < 4:
        return 0.0

    g, p = g[:n], p[:n]

    g -= g.mean()
    p -= p.mean()

    ng, np_ = np.linalg.norm(g), np.linalg.norm(p)
    if ng == 0 or np_ == 0:
        return 0.0

    best_corr = 0.0
    best_lag = 0

    for lag in range(-max_lag, max_lag + 1):

        if lag < 0:
            g_seg = g[-lag:]
            p_seg = p[:n + lag]
        elif lag > 0:
            g_seg = g[:n - lag]
            p_seg = p[lag:]
        else:
            g_seg = g
            p_seg = p

        if len(g_seg) < 3:
            continue

        corr = np.dot(g_seg, p_seg) / (
            np.linalg.norm(g_seg) * np.linalg.norm(p_seg)
        )

        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_corr <= 0:
        return 0.0

    # Prefer lead (negative lag)
    lag_factor = 1.0 if best_lag < 0 else 0.8 if best_lag == 0 else 0.5

    return max(0.0, min(1.0, best_corr * lag_factor))


# -------------------------
# PID Ranker (FINAL)
# -------------------------

class PidStatisticalRanker:

    def __init__(self):
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
        top_k=15,
    ):
        """
        Main RCA ranking entry point.
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

        # ----------------------------------------------------
        # Process snapshot + ETW metrics
        # ----------------------------------------------------

        for pid, events in buckets.items():

            try:
                proc = psutil.Process(pid)

                name = proc.name()
                cmdline = " ".join(proc.cmdline())

                # ✅ NON-BLOCKING CPU SAMPLING
                cpu_pct = proc.cpu_percent(interval=None)
                ram_pct = proc.memory_percent()

            except Exception:
                name = "Unknown"
                cmdline = ""
                cpu_pct = 0.0
                ram_pct = 0.0

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


        # ----------------------------------------------------
        # Feature shaping
        # ----------------------------------------------------

        for p in pid_rows:
            p["net_bytes_log"] = np.log1p(_safe_float(p["net_bytes"]))
            p["disk_bytes_log"] = np.log1p(_safe_float(p["disk_bytes"]))


        # ----------------------------------------------------
        # Robust Z-score anomaly
        # ----------------------------------------------------

        anomaly_feats = [
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
        for feat in anomaly_feats:
            vals = [_safe_float(p[feat]) for p in pid_rows]
            med = median(vals)
            mad = median(abs(v - med) for v in vals)
            stats[feat] = (med, mad)

        z_anomaly_raws = []

        for p in pid_rows:
            z_vals = []
            for feat in anomaly_feats:
                med, mad = stats[feat]
                z_vals.append(_robust_z_score(_safe_float(p[feat]), med, mad))

            z_val = sum(z_vals) / len(z_vals)
            p["z_anomaly"] = z_val
            z_anomaly_raws.append(z_val)


        # ----------------------------------------------------
        # Mahalanobis anomaly
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

        X = np.array(
            [
                [_safe_float(p[f]) for f in mahal_feats]
                for p in pid_rows
            ],
            dtype=float
        )

        mahal_raws = _mahalanobis_scores(X)

        for p, m in zip(pid_rows, mahal_raws):
            p["mahalanobis"] = float(m)


        # ----------------------------------------------------
        # Energy contribution scores (✅ CLIPPED)
        # ----------------------------------------------------

        denom_cpu = max(spike_cpu, 1.0)
        denom_ram = max(spike_ram, 1.0)
        denom_disk = max(total_disk_bytes, 1.0)
        denom_net = max(total_net_bytes, 1.0)

        energy_raws = []

        for p in pid_rows:

            cpu = min(_safe_float(p["cpu_pct"]) / denom_cpu, 1.5)
            ram = min(_safe_float(p["ram_pct"]) / denom_ram, 1.5)
            disk = min(_safe_float(p["disk_bytes"]) / denom_disk, 1.5)
            net = min(_safe_float(p["net_bytes"]) / denom_net, 1.5)

            energy = (
                0.4 * cpu +
                0.3 * ram +
                0.15 * disk +
                0.15 * net
            )

            p["energy_raw"] = energy
            energy_raws.append(energy)


        # ----------------------------------------------------
        # Correlation scoring
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
                spike_cpu, spike_ram,
                1, 1, 1, 1, 1, 1, 1,
            ]

            cos_corr = _cosine_similarity(pid_vec, spike_vec)

            series = pid_cpu_series.get(p["pid"]) if pid_cpu_series else None

            lead_score = _lead_lag_score(global_cpu_series, series)

            corr = 0.7 * cos_corr + 0.3 * lead_score

            p["cosine_correlation"] = cos_corr
            p["lead_lag_score"] = lead_score
            p["correlation_raw"] = corr

            corr_raws.append(corr)


        # ----------------------------------------------------
        # Normalization helpers
        # ----------------------------------------------------

        def _normalize(vals):
            arr = np.asarray(vals, dtype=float)

            if arr.size == 0:
                return [0.0]

            mx = arr.max()
            if mx <= 0:
                return [0.0 for _ in arr]

            return [float(v / mx) for v in arr]


        z_norm = _normalize(z_anomaly_raws)
        m_norm = _normalize(mahal_raws)
        e_norm = _normalize(energy_raws)
        c_norm = _normalize(corr_raws)


        anomaly_norm = [
            0.5 * z + 0.5 * m
            for z, m in zip(z_norm, m_norm)
        ]


        severity_boost = 1.25 if spike_cpu > 85 or spike_ram > 80 else 1.0

        finals = []

        for p, a, e, c in zip(pid_rows, anomaly_norm, e_norm, c_norm):

            raw = severity_boost * (
                self.weight_anomaly * a +
                self.weight_energy * e +
                self.weight_correlation * c
            )

            p["anomaly_score"] = round(a, 4)
            p["energy_score"] = round(e, 4)
            p["correlation_score"] = round(c, 4)

            finals.append(raw)


        max_final = max(finals) if finals else 1.0
        max_final = max(max_final, 1e-9)

        ranked = []

        for p, v in zip(pid_rows, finals):
            p["final_score"] = round(min(1.0, v / max_final), 4)
            ranked.append(p)

        ranked.sort(key=lambda x: x["final_score"], reverse=True)

        return ranked[:top_k]
