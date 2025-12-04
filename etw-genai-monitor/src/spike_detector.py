from collections import deque
from statistics import mean, pstdev
from datetime import datetime, timezone, timedelta


class SpikeDetector:
    """
    CPU + RAM spike detector with:
    - rolling baseline
    - z-score candidate detection for CPU & RAM
    - derivative candidate detection for CPU
    - sustained threshold confirmation
    - spike classification + severity scoring
    - cooldown to avoid double triggers
    """

    def __init__(
        self,
        baseline_window=300,
        sample_interval=1.0,
        z_score=2.5,
        derivative_threshold=5.0,
        derivative_len=3,
        confirm_seconds=30,
        cpu_threshold=90.0,
        ram_threshold=80.0,
        cooldown_seconds=45,
    ):
        self.window = deque(maxlen=int(baseline_window / sample_interval))
        self.sample_interval = sample_interval
        self.z = z_score
        self.deriv_thresh = derivative_threshold
        self.deriv_len = derivative_len
        self.confirm_seconds = confirm_seconds
        self.cpu_threshold = cpu_threshold
        self.ram_threshold = ram_threshold
        self.cooldown = timedelta(seconds=cooldown_seconds)

        self.last_cpu_values = deque(maxlen=derivative_len + 2)

        # ✅ FIX 1
        self.confirm_buffer = deque(
            maxlen=int(confirm_seconds / sample_interval)
        )

        self.last_spike_time = None

    # -----------------------------------------------------

    def add_sample(self, sample):
        self.window.append(sample)
        self.last_cpu_values.append(sample["cpu"])

        self.confirm_buffer.append(
            sample["cpu"] >= self.cpu_threshold or
            sample["ram"] >= self.ram_threshold
        )

    # -----------------------------------------------------

    def _mu_sigma(self, key="cpu"):
        # ✅ FIX 2
        if len(self.window) < 10:
            return None, None

        vals = [s[key] for s in self.window]
        return mean(vals), pstdev(vals)

    # -----------------------------------------------------

    def _candidate_zscore(self, key="cpu"):
        mu, sigma = self._mu_sigma(key)

        if mu is None or sigma is None or sigma <= 0.001:
            return None

        threshold = mu + self.z * sigma

        # Scan backwards for spike seed
        for s in reversed(self.window):
            if s[key] >= threshold:
                return s

        return None

    # -----------------------------------------------------

    def _candidate_derivative(self):
        lv = list(self.last_cpu_values)

        if len(lv) < self.deriv_len + 1:
            return None

        deltas = [lv[i] - lv[i - 1] for i in range(1, len(lv))]
        tail = deltas[-self.deriv_len:]

        # ✅ FIX 3 — average slope instead of strict all()
        avg_slope = sum(tail) / len(tail)

        if avg_slope > self.deriv_thresh:
            start_value = lv[-(self.deriv_len + 1)]

            for s in reversed(self.window):
                if s["cpu"] >= start_value:
                    return s

        return None

    # -----------------------------------------------------

    def _cooldown_passed(self):
        if not self.last_spike_time:
            return True

        return datetime.now(timezone.utc) - self.last_spike_time > self.cooldown

    # -----------------------------------------------------

    def check(self):
        if not self.window or not self._cooldown_passed():
            return False, {}

        cand_cpu = self._candidate_zscore("cpu")
        cand_ram = self._candidate_zscore("ram")
        cand_deriv = cand_cpu or self._candidate_derivative()

        cand = cand_cpu or cand_ram or cand_deriv

        if (
            cand
            and len(self.confirm_buffer) == self.confirm_buffer.maxlen
            and all(self.confirm_buffer)
        ):
            latest = self.window[-1]

            spike_type = (
                "mixed"
                if latest["cpu"] >= self.cpu_threshold and latest["ram"] >= self.ram_threshold
                else "cpu"
                if latest["cpu"] >= self.cpu_threshold
                else "ram"
            )

            severity = max(
                0.0,
                (latest["cpu"] - self.cpu_threshold)
                + (latest["ram"] - self.ram_threshold)
            )

            self.last_spike_time = datetime.now(timezone.utc)
            self.confirm_buffer.clear()

            info = {
                "start_time": cand["ts"],
                "confirm_time": self.last_spike_time.isoformat(),
                "spike_type": spike_type,
                "severity_score": round(severity, 2),
                "cpu_at_confirm": latest["cpu"],
                "ram_at_confirm": latest["ram"],
            }

            return True, info

        return False, {}
