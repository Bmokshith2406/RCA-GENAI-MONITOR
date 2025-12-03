import React, { useEffect, useState, useCallback } from "react";
import { Routes, Route, Link } from "react-router-dom";
import SpikeDetail from "./SpikeDetail";
import LiveEvents from "./LiveEvents";

/* -----------------------------------
 * HELPER FUNCTIONS
 * ----------------------------------- */

function formatTimestamp(isoString) {
  if (!isoString) return "N/A";
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;

    const timeOnly = date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const dateOnly = date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
    return `${dateOnly} @ ${timeOnly}`;
  } catch {
    return isoString;
  }
}

const getRcaPillStyle = (isResolved) =>
  isResolved ? pillStyle("success") : pillStyle("pending");

/* -----------------------------------
 * COMPONENTS
 * ----------------------------------- */

function DashboardView() {
  const [spikes, setSpikes] = useState([]);
  const [latestRca, setLatestRca] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (spikes.length === 0 && !error) setLoading(true);

    try {
      const [spikesRes, rcaRes] = await Promise.all([
        fetch("/api/spikes"),
        fetch("/api/latest-rca"),
      ]);

      if (!spikesRes.ok)
        throw new Error(`Spikes API error! Status: ${spikesRes.status}`);
      if (!rcaRes.ok)
        throw new Error(`RCA API error! Status: ${rcaRes.status}`);

      const spikesJson = await spikesRes.json();
      const rcaJson = await rcaRes.json();

      const sortedSpikes = (spikesJson.spikes || []).sort(
        (a, b) =>
          new Date(b.detected_at) - new Date(a.detected_at)
      );

      setSpikes(sortedSpikes);
      setLatestRca(rcaJson.latest_rca || null);
      setError(null);
    } catch (e) {
      console.error("Dashboard fetch failed:", e);
      setError(
        `Failed to fetch dashboard data. Check console for details. (Error: ${e.message})`
      );
    } finally {
      setLoading(false);
    }
  }, [spikes.length, error]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  return (
    <div style={rootStyle}>
      {/* ================= HERO & STATUS ================= */}
      <header style={heroWrap}>
        <div>
          <h1 style={titleStyle}>ETW GenAI Kernel Monitor</h1>
          <p style={subtitleStyle}>
            Live CPU & RAM spike detection · ETW-powered RCA · Powered by Gemini
            2.5 Flash
          </p>
        </div>

        <div style={statusChip}>
          <span style={pulseDot} />
          <span style={{ marginLeft: "4px" }}>LIVE</span>
        </div>
      </header>

      {/* ================= LOADING / ERROR ================= */}
      {(loading || error) && (
        <div style={infoBox(error ? "error" : "info")}>
          {loading && <p>Loading telemetry and configuration data...</p>}
          {error && <p>API Error: {error}</p>}
        </div>
      )}

      {/* ================= MAIN GRID ================= */}
      <div style={gridStyle}>
        {/* ================= SPIKES ================= */}
        <div style={cardStyle}>
          <h2 style={cardTitle}>
            <span style={titleIcon}>📊</span> Spike History
          </h2>
          <SpikeTable spikes={spikes} loading={loading} />
        </div>

        {/* ================= RCA ================= */}
        <div style={cardStyle}>
          <h2 style={cardTitle}>
            <span style={titleIcon}>🧠</span> Latest RCA
          </h2>
          <RcaPanel latestRca={latestRca} loading={loading} />
        </div>
      </div>

      <div style={{ margin: "2.5rem 0" }}>
        <LiveEvents />
      </div>

      <footer style={footerStyle}>
        Built by Mokshith · Deloitte Innovation
      </footer>
    </div>
  );
}

function SpikeTable({ spikes, loading }) {
  if (loading) return null;

  if (spikes.length === 0)
    return <p style={mutedText}>No spikes detected yet. Monitoring is active.</p>;

  return (
    <div style={tableWrap}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Detected Time</th>
            <th style={thStyle}>Max CPU%</th>
            <th style={thStyle}>Max RAM%</th>
            <th style={thStyle}>Status</th>
          </tr>
        </thead>
        <tbody>
          {spikes.map((s) => (
            <tr key={s.id} style={rowStyle}>
              <td style={tdStyle}>
                <Link style={linkStyle} to={`/spike/${s.id}`}>
                  #{s.id}
                </Link>
              </td>
              <td style={tdStyle}>{formatTimestamp(s.detected_at)}</td>
              <td style={tdStyle}>
                <span style={highlightData("cpu")}>
                  {s.cpu_at_confirm?.toFixed(1)}%
                </span>
              </td>
              <td style={tdStyle}>
                <span style={highlightData("ram")}>
                  {s.ram_at_confirm?.toFixed(1)}%
                </span>
              </td>
              <td style={tdStyle}>
                <span style={getRcaPillStyle(!!s.rca)}>
                  {s.rca ? "RESOLVED" : "PENDING"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RcaPanel({ latestRca, loading }) {
  if (loading) return null;

  if (!latestRca)
    return (
      <p style={mutedText}>Awaiting a confirmed spike for analysis…</p>
    );

  const culprit = latestRca.culprit_process;
  const impact = latestRca.resource_impact;

  return (
    <div style={stack}>
      <section>
        <h3 style={subTitleStyle}>
          <span style={subTitleIcon}>📝</span>
          Root Cause Summary
        </h3>

        <p style={bodyText}>{latestRca.cause_summary}</p>

        <p style={confidenceText}>
          AI Confidence: {(latestRca.confidence * 100 || 0).toFixed(1)}%
        </p>
      </section>

      {culprit && (
        <section style={highlightBox}>
          <h3 style={subTitleStyle}>
            <span style={subTitleIcon}>🔥</span>
            Primary Culprit
          </h3>

          <div style={culpritDetail}>
            <strong style={culpritName}>{culprit.name}</strong>
            <span style={mutedText}>(PID {culprit.pid})</span>
          </div>

          {culprit.cmdline && (
            <p style={cmdText}>{culprit.cmdline}</p>
          )}

          <div style={metricsRow}>
            <span style={metricData}>
              CPU:{" "}
              <span style={highlightData("cpu")}>
                {culprit.cpu_pct?.toFixed(1)}%
              </span>
            </span>

            <span style={metricData}>
              RAM:{" "}
              <span style={highlightData("ram")}>
                {culprit.ram_pct?.toFixed(1)}%
              </span>
            </span>
          </div>
        </section>
      )}

      {impact && (
        <section>
          <h3 style={subTitleStyle}>
            <span style={subTitleIcon}>📈</span>
            Resource Impact
          </h3>

          <div style={metricsRow}>
            <span style={metricData}>
              System CPU Spike:{" "}
              <span style={highlightData("cpu")}>
                {impact.cpu_spike_percent?.toFixed(1)}%
              </span>
            </span>

            <span style={metricData}>
              System RAM Spike:{" "}
              <span style={highlightData("ram")}>
                {impact.ram_spike_percent?.toFixed(1)}%
              </span>
            </span>
          </div>
        </section>
      )}

      {latestRca.ranked_suspects?.length > 0 && (
        <section>
          <h3 style={subTitleStyle}>
            <span style={subTitleIcon}>🕵️</span>
            Other Suspects
          </h3>

          <ul style={listStyle}>
            {latestRca.ranked_suspects.slice(0, 5).map((r, i) => (
              <li key={i}>
                PID {r.pid} – {r.name} (Score:{" "}
                <span style={highlightData("score")}>
                  {r.score?.toFixed(3)}
                </span>
                )
              </li>
            ))}
          </ul>
        </section>
      )}

      {latestRca.recs?.length > 0 && (
        <section>
          <h3 style={subTitleStyle}>
            <span style={subTitleIcon}>🛠️</span>
            Recommendations
          </h3>

          <ul style={listStyle}>
            {latestRca.recs.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ================= ROUTER ================= */

const App = () => (
  <Routes>
    <Route path="/" element={<DashboardView />} />
    <Route path="/spike/:id" element={<SpikeDetail />} />
  </Routes>
);

/* ================= STYLES ================= */

// Deloitte green + black theme
const PRIMARY = "#43B02A";
const SECONDARY = "#9CA3AF";
const SUCCESS = "#43B02A";
const DANGER = "#DC2626";
const CPU_COLOR = "#16A34A";
const RAM_COLOR = "#22C55E";

const BASE_BG = "#000000";
const CARD_BG = "#0B0F0C";
const BORDER_COLOR = "#1F2937";

const rootStyle = {
  fontFamily: "Inter, system-ui, sans-serif",
  background: BASE_BG,
  color: "#e5e7eb",
  minHeight: "100vh",
  padding: "2rem",
};

const heroWrap = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  background: CARD_BG,
  padding: "1.5rem 2rem",
  borderRadius: "12px",
  border: `1px solid ${BORDER_COLOR}`,
  marginBottom: "2rem",
};

const titleStyle = { fontSize: "1.8rem", margin: 0 };
const subtitleStyle = {
  color: SECONDARY,
  marginTop: "0.5rem",
};
const titleIcon = { marginRight: "8px", color: PRIMARY };

const statusChip = {
  background: PRIMARY + "22",
  color: PRIMARY,
  borderRadius: "999px",
  padding: "6px 14px",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
};

const pulseDot = {
  width: "8px",
  height: "8px",
  borderRadius: "50%",
  backgroundColor: PRIMARY,
};

const infoBox = (type) => ({
  padding: "1rem",
  borderRadius: "8px",
  marginBottom: "1.5rem",
  border: `1px solid ${type === "error" ? DANGER : PRIMARY}`,
  background: type === "error" ? DANGER + "22" : PRIMARY + "22",
  color: type === "error" ? DANGER : PRIMARY,
});

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "3fr 2fr",
  gap: "2rem",
};

const cardStyle = {
  background: CARD_BG,
  borderRadius: "12px",
  border: `1px solid ${BORDER_COLOR}`,
  padding: "1.5rem",
};

const cardTitle = {
  fontSize: "1.25rem",
  marginBottom: "1rem",
  borderBottom: `1px solid ${BORDER_COLOR}`,
  paddingBottom: "0.75rem",
  display: "flex",
  alignItems: "center",
};

const tableWrap = { maxHeight: "300px", overflowY: "auto" };
const tableStyle = { width: "100%", borderCollapse: "collapse" };

const thStyle = {
  padding: "0.75rem",
  color: SECONDARY,
  borderBottom: `1px solid ${BORDER_COLOR}`,
};

const tdStyle = {
  padding: "0.75rem",
  borderBottom: `1px solid ${BORDER_COLOR}`,
};

const rowStyle = {};
const linkStyle = {
  color: PRIMARY,
  fontWeight: 600,
  textDecoration: "none",
};

const pillStyle = (type) => ({
  background: PRIMARY + "22",
  color: PRIMARY,
  borderRadius: "999px",
  padding: "4px 10px",
  fontSize: "0.7rem",
  fontWeight: 700,
});

const subTitleStyle = {
  fontWeight: 600,
  marginBottom: "0.5rem",
  display: "flex",
};

const subTitleIcon = { marginRight: "6px", color: PRIMARY };

const stack = {
  display: "flex",
  flexDirection: "column",
  gap: "1.5rem",
};

const highlightBox = {
  border: `1px solid ${PRIMARY}40`,
  borderRadius: "8px",
  padding: "1rem",
};

const culpritDetail = {
  display: "flex",
  alignItems: "baseline",
  gap: "8px",
};

const culpritName = { fontSize: "1.1rem", color: "#ffffff" };

const metricsRow = {
  display: "flex",
  gap: "1.5rem",
  marginTop: "0.5rem",
};

const metricData = {
  fontSize: "0.85rem",
  color: SECONDARY,
};

const highlightData = (type) => ({
  color:
    type === "cpu"
      ? CPU_COLOR
      : type === "ram"
      ? RAM_COLOR
      : PRIMARY,
  fontWeight: 700,
});

const mutedText = { color: SECONDARY };
const bodyText = { color: "#e5e7eb" };

const confidenceText = {
  color: SUCCESS,
  fontWeight: 600,
};

const cmdText = {
  color: SECONDARY,
  fontSize: "0.8rem",
  fontFamily: "monospace",
};

const listStyle = { paddingLeft: "1.25rem" };

const footerStyle = {
  marginTop: "2rem",
  borderTop: `1px solid ${BORDER_COLOR}`,
  paddingTop: "1rem",
  textAlign: "center",
  color: SECONDARY,
  fontSize: "0.85rem",
};

export default App;
