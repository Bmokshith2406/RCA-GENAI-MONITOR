import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Routes, Route, Link } from "react-router-dom";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Brush,
} from "recharts";
import SpikeDetail from "./SpikeDetail";

/* ==================================================
   CONFIG / COLORS
================================================== */

const PRIMARY = "#43B02A";
const SECONDARY = "#9CA3AF";
const CPU_COLOR = "#34D399";
const RAM_COLOR = "#60A5FA";
const SPIKE_COLOR = "#F97316";

const BASE_BG = "#0A0A0A";
const CARD_BG = "#1A1A1A";
const BORDER_COLOR = "#333";

/* ==================================================
   TIME UTILS
================================================== */

const parseTs = (t) => (isNaN(new Date(t)) ? null : new Date(t));

const formatTime = (t) =>
  parseTs(t)?.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }) || "";

/* ==================================================
   DASHBOARD
================================================== */

function DashboardView() {
  const [telemetry, setTelemetry] = useState([]);
  const [spikes, setSpikes] = useState([]);
  const [latestRca, setLatestRca] = useState(null);

  /* ------------------------------
     LIVE POLLING
  ------------------------------- */

  const pollData = useCallback(async () => {
    try {
      const [t, s, r] = await Promise.all([
        fetch("/api/telemetry/window?seconds=60"),
        fetch("/api/spikes"),
        fetch("/api/latest-rca"),
      ]);

      if (!t.ok || !s.ok || !r.ok) throw new Error("API failure");

      const telemetryJson = await t.json();
      const spikesJson = await s.json();
      const rcaJson = await r.json();

      setTelemetry(telemetryJson.samples || []);
      setSpikes(
        (spikesJson.spikes || []).sort(
          (a, b) => new Date(b.detected_at) - new Date(a.detected_at)
        )
      );

      setLatestRca(rcaJson.latest_rca || null);
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, []);

  useEffect(() => {
    pollData();
    const t = setInterval(pollData, 1000);
    return () => clearInterval(t);
  }, [pollData]);

  const last = telemetry.at(-1) || { cpu: 0, ram: 0 };

  return (
    <div style={{ background: BASE_BG, minHeight: "100vh", color: "#fff", padding: "2rem" }}>
      {/* HEADER */}
      <header style={headerStyle}>
        <div>
          <h1 style={{ margin: 0 }}>ETW GenAI Kernel Monitor</h1>
          <p style={{ color: SECONDARY }}>
            Live CPU & RAM · Spike Detection · RCA AI
          </p>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <StatBadge label="CPU" val={`${last.cpu?.toFixed(1)}%`} color={CPU_COLOR} />
          <StatBadge label="RAM" val={`${last.ram?.toFixed(1)}%`} color={RAM_COLOR} />

          <div style={liveBadgeStyle}>LIVE</div>
        </div>
      </header>

      {/* CHART */}
      <ChartCard telemetry={telemetry} spikes={spikes} />

      {/* GRID */}
      <div style={gridStyle}>
        <SpikeTable spikes={spikes} />
        <RcaPanel latestRca={latestRca} />
      </div>

      {/* FOOTER */}
      <footer style={footerStyle}>
        Built by Mokshith · Deloitte Innovation
      </footer>
    </div>
  );
}

/* ==================================================
   STAT BADGE
================================================== */

const StatBadge = ({ label, val, color }) => (
  <div style={{ background: color + "22", color, padding: "6px 14px", borderRadius: "10px", fontWeight: 700 }}>
    {label}: {val}
  </div>
);

/* ==================================================
   CHART PANEL
================================================== */

const ChartCard = ({ telemetry, spikes }) => {
  const spikeTimes = new Set(spikes.map((s) => formatTime(s.detected_at)));

  const data = useMemo(() => {
    return telemetry.map((p) => ({
      t: formatTime(p.ts),
      cpu: p.cpu,
      ram: p.ram,
      spike: spikeTimes.has(formatTime(p.ts)),
    }));
  }, [telemetry, spikes]);

  if (!data.length) return null;

  return (
    <div style={cardStyle}>
      <h2 style={{ marginBottom: "0.8rem" }}>📊 Live System Telemetry</h2>

      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CPU_COLOR} stopOpacity={0.9} />
              <stop offset="100%" stopColor={CPU_COLOR} stopOpacity={0.15} />
            </linearGradient>

            <linearGradient id="ramGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={RAM_COLOR} stopOpacity={0.9} />
              <stop offset="100%" stopColor={RAM_COLOR} stopOpacity={0.15} />
            </linearGradient>
          </defs>

          <XAxis dataKey="t" tick={{ fill: SECONDARY, fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fill: SECONDARY }} />

          <Tooltip
            contentStyle={{
              backgroundColor: CARD_BG,
              border: `1px solid ${BORDER_COLOR}`,
            }}
          />
          <Legend />

          <Area
            dataKey="cpu"
            name="CPU %"
            stroke={CPU_COLOR}
            fill="url(#cpuGrad)"
            dot={<SpikeDot />}
            isAnimationActive={false}
          />

          <Area
            dataKey="ram"
            name="RAM %"
            stroke={RAM_COLOR}
            fill="url(#ramGrad)"
            isAnimationActive={false}
          />

          <Brush stroke={PRIMARY} height={22} travellerWidth={10} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

/* ==================================================
   SPIKE DOT
================================================== */

const SpikeDot = ({ cx, cy, payload }) =>
  payload?.spike ? (
    <>
      <circle r={7} cx={cx} cy={cy} fill={SPIKE_COLOR + "55"} />
      <circle r={4} cx={cx} cy={cy} fill={SPIKE_COLOR} />
    </>
  ) : null;

/* ==================================================
   SPIKE TABLE
================================================== */

const SpikeTable = ({ spikes }) => (
  <div style={cardStyle}>
    <h3 style={{ marginBottom: "1rem" }}>Spike History</h3>

    {!spikes.length ? (
      <p style={{ color: SECONDARY }}>No spikes detected yet.</p>
    ) : (
      <div style={{ maxHeight: 280, overflowY: "auto" }}>
        {spikes.map((s) => (
          <div key={s.id} style={rowStyle}>
            <Link to={`/spike/${s.id}`} style={{ color: PRIMARY }}>
              #{s.id}
            </Link>

            <span style={{ color: CPU_COLOR }}>{s.cpu_at_confirm.toFixed(1)}%</span>
            <span style={{ color: RAM_COLOR }}>{s.ram_at_confirm.toFixed(1)}%</span>

            <span style={badgeStyle(s.rca)}>
              {s.rca ? "RESOLVED" : "PENDING"}
            </span>
          </div>
        ))}
      </div>
    )}
  </div>
);

/* ==================================================
   RCA PANEL
================================================== */

const RcaPanel = ({ latestRca }) => (
  <div style={cardStyle}>
    <h3>Latest RCA</h3>

    {!latestRca ? (
      <p style={{ color: SECONDARY }}>Awaiting RCA analysis...</p>
    ) : (
      <>
        <p style={{ lineHeight: 1.5 }}>{latestRca.cause_summary}</p>

        <div style={confidenceStyle}>
          AI Confidence {(latestRca.confidence * 100).toFixed(1)}%
        </div>
      </>
    )}
  </div>
);

/* ==================================================
   STYLES
================================================== */

const headerStyle = {
  background: CARD_BG,
  padding: "1.5rem",
  borderRadius: 12,
  border: `1px solid ${BORDER_COLOR}`,
  marginBottom: "1.5rem",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const liveBadgeStyle = {
  padding: "6px 14px",
  background: PRIMARY + "22",
  borderRadius: 999,
  color: PRIMARY,
  fontWeight: 700,
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "3fr 2fr",
  gap: "1.5rem",
  marginTop: "1.5rem",
};

const cardStyle = {
  background: CARD_BG,
  padding: "1.5rem",
  borderRadius: 12,
  border: `1px solid ${BORDER_COLOR}`,
};

const rowStyle = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr 1fr 1fr",
  gap: "0.75rem",
  padding: "8px 0",
  borderBottom: `1px solid ${BORDER_COLOR}`,
  alignItems: "center",
};

const badgeStyle = (rca) => ({
  background: (rca ? PRIMARY : SPIKE_COLOR) + "22",
  color: rca ? PRIMARY : SPIKE_COLOR,
  padding: "3px 10px",
  borderRadius: 999,
  fontWeight: 700,
  fontSize: "0.75rem",
  textAlign: "center",
});

const confidenceStyle = {
  marginTop: "1rem",
  paddingTop: "1rem",
  borderTop: `1px dashed ${BORDER_COLOR}`,
  color: PRIMARY,
  fontWeight: 700,
};

const footerStyle = {
  marginTop: "3rem",
  textAlign: "center",
  color: SECONDARY,
  fontSize: "0.9rem",
};

/* ==================================================
   ROUTER
================================================== */

const App = () => (
  <Routes>
    <Route path="/" element={<DashboardView />} />
    <Route path="/spike/:id" element={<SpikeDetail />} />
  </Routes>
);

export default App;
