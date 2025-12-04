import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";

/* -----------------------------------
 * STYLES REFACTOR & CONFIG (FIXED)
 * ----------------------------------- */

const PRIMARY_COLOR = "#43B02A"; // Success/Action color (Green)
const SUCCESS_COLOR = "#22C55E";
const WARNING_COLOR = "#FACC15";
const DANGER_COLOR = "#DC2626";

const CPU_COLOR = "#34D399"; // Brighter green for CPU
const RAM_COLOR = "#60A5FA"; // Blue for RAM

const BASE_BG = "#0A0A0A"; // Darker base
const CARD_BG = "#1A1A1A"; // Card background
const BORDER_COLOR = "#333333";
const TEXT_LIGHT = "#E5E7EB";
const TEXT_MUTED = "#9CA3AF";
// FIX: Added the missing DARKER_BG definition
const DARKER_BG = "#0B0F0C"; 

const styles = {
  // --- Page Layout ---
  page: {
    background: BASE_BG,
    color: TEXT_LIGHT,
    minHeight: "100vh",
    padding: "2rem",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  header: {
    marginBottom: "2rem",
    borderBottom: `1px solid ${BORDER_COLOR}`,
    paddingBottom: "1.5rem",
  },
  backLink: {
    color: TEXT_MUTED,
    textDecoration: "none",
    fontSize: "0.9rem",
    "&:hover": { color: PRIMARY_COLOR },
  },
  title: {
    fontSize: "2.5rem",
    margin: "0.5rem 0 0.25rem 0",
    display: "flex",
    alignItems: "center",
  },
  titleIcon: {
    marginRight: "12px",
    color: DANGER_COLOR, // Using DANGER for '💥' effect
  },
  subtitle: { color: TEXT_MUTED, margin: 0 },
  
  // --- Grid and Metrics ---
  metricGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "1.5rem",
    marginBottom: "2rem",
  },
  metric: {
    padding: "1rem",
    borderRadius: "8px",
    background: CARD_BG,
    borderLeft: `4px solid`,
    display: "flex",
    flexDirection: "column",
  },
  metricLabel: {
    fontSize: "0.85rem",
    color: TEXT_MUTED,
    marginBottom: "0.25rem",
  },
  metricValue: {
    fontSize: "1.5rem",
    fontWeight: 700,
  },
  
  // --- Cards ---
  card: {
    borderRadius: "12px",
    border: `1px solid ${BORDER_COLOR}`,
    marginBottom: "1.5rem",
    overflow: 'hidden', // Necessary for Raw ETW Card
  },
  cardTitle: {
    display: "flex",
    alignItems: "center",
    fontSize: "1.2rem",
    borderBottom: `1px solid ${BORDER_COLOR}55`,
    padding: "0.5rem 1.5rem",
    background: BORDER_COLOR + '33', // Slight shading for title bar
    margin: 0,
  },
  cardTitleIcon: { marginRight: "10px" },
  cardContent: (paddingOverride) => ({
    padding: paddingOverride ? paddingOverride : "1.5rem",
    lineHeight: 1.6,
  }),
  
  // --- RCA Details ---
  bodyText: { color: TEXT_LIGHT, margin: "0 0 1rem 0" },
  confidence: {
    borderTop: `1px dashed ${BORDER_COLOR}55`,
    paddingTop: "1rem",
    marginTop: "1rem",
    color: TEXT_MUTED,
  },
  
  // --- Culprit ---
  culpritContainer: {
    background: BASE_BG,
    padding: "1rem",
    borderRadius: "8px",
    border: `1px solid ${BORDER_COLOR}55`,
    marginBottom: "1rem",
  },
  culpritHeader: {
    display: "flex",
    alignItems: "baseline",
    gap: "10px",
    marginBottom: "0.5rem",
  },
  culpritName: {
    fontSize: "1.1rem",
    color: PRIMARY_COLOR,
  },
  cmdText: {
    fontSize: "0.8rem",
    fontFamily: "monospace",
    color: TEXT_MUTED,
    margin: "0 0 0.75rem 0",
    wordBreak: 'break-all',
  },
  culpritMetrics: {
    display: "flex",
    gap: "1rem",
    fontSize: "0.9rem",
  },
  metricLabelValue: { color: TEXT_MUTED },
  
  // --- Suspects ---
  list: {
    listStyleType: "disc",
    paddingLeft: "20px",
    margin: 0,
  },
  
  // --- Raw Data ---
  rawHeader: {
    fontSize: "1.8rem",
    color: TEXT_LIGHT,
    borderBottom: `1px solid ${BORDER_COLOR}`,
    paddingBottom: "0.5rem",
    marginBottom: "1.5rem",
    marginTop: "3rem",
  },
  eventList: {
    maxHeight: "400px",
    overflowY: "auto",
    padding: 0, // Card handles padding
  },
  eventBlock: {
    margin: 0,
    padding: "1rem 1.5rem",
    fontSize: "0.7rem",
    fontFamily: "monospace",
    whiteSpace: "pre-wrap",
    wordBreak: "break-all",
    background: DARKER_BG, // <-- This is where the error occurred
    borderBottom: `1px solid ${BORDER_COLOR}55`,
  },
  codeBlock: {
    margin: 0,
    padding: "1.5rem",
    fontSize: "0.75rem",
    fontFamily: "monospace",
    whiteSpace: "pre-wrap",
    wordBreak: "break-all",
    color: WARNING_COLOR, // Highlight JSON slightly
  },

  // --- Helpers ---
  mutedText: { color: TEXT_MUTED },
  errorText: { color: DANGER_COLOR, padding: "2rem" },
  loadingText: { color: WARNING_COLOR, padding: "2rem" },
  highlightData: (type) => {
    let color;
    switch (type) {
      case "cpu":
        color = CPU_COLOR;
        break;
      case "ram":
        color = RAM_COLOR;
        break;
      case "disk":
        color = WARNING_COLOR;
        break;
      case "score":
      case "confidence":
        color = PRIMARY_COLOR;
        break;
      default:
        color = TEXT_LIGHT;
    }
    return { fontWeight: 700, color: color };
  },
};

// Helper function to resolve styles
const style = (name) => styles[name];
const highlightData = (type) => styles.highlightData(type);
const cardContentStyle = (paddingOverride) => styles.cardContent(paddingOverride);


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
      second: "2-digit",
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

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || isNaN(bytes) || bytes < 0) return "—";
  if (bytes === 0) return "0 B";

  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/* -----------------------------------
 * SUB-COMPONENTS
 * ----------------------------------- */

function Metric({ label, value, accent }) {
  return (
    <div style={{ ...style('metric'), borderLeftColor: accent || PRIMARY_COLOR }}>
      <span style={style('metricLabel')}>{label}</span>
      <strong style={{ ...style('metricValue'), color: accent || PRIMARY_COLOR }}>
        {value}
      </strong>
    </div>
  );
}

function Card({ title, children, highlight, icon }) {
  // Determine if padding should be zero (for raw data lists/blocks)
  const isRawDataCard = title.includes("Raw ETW Events") || title.includes("JSON Payload");
  
  return (
    <section
      style={{
        ...style('card'),
        borderLeftColor: highlight ? PRIMARY_COLOR : BORDER_COLOR,
        background: highlight ? `${BASE_BG}e6` : CARD_BG,
      }}
    >
      <h3 style={style('cardTitle')}>
        <span style={style('cardTitleIcon')}>{icon}</span>
        {title}
      </h3>

      <div style={isRawDataCard ? cardContentStyle("0") : cardContentStyle()}>
        {children}
      </div>
    </section>
  );
}

function CulpritDetails({ culprit }) {
  if (!culprit || !culprit.pid) return null;

  return (
    <div style={style('culpritContainer')}>
      <div style={style('culpritHeader')}>
        <strong style={style('culpritName')}>{culprit.name}</strong>
        <span style={style('mutedText')}>(PID {culprit.pid})</span>
      </div>

      {culprit.cmdline && <p style={style('cmdText')}>{culprit.cmdline}</p>}

      <div style={style('culpritMetrics')}>
        <span style={style('metricLabelValue')}>
          CPU:{" "}
          <span style={highlightData("cpu")}>
            {typeof culprit.cpu_pct === "number"
              ? culprit.cpu_pct.toFixed(1)
              : "?"}
            %
          </span>
        </span>

        <span style={style('metricLabelValue')}>
          RAM:{" "}
          <span style={highlightData("ram")}>
            {typeof culprit.ram_pct === "number"
              ? culprit.ram_pct.toFixed(1)
              : "?"}
            %
          </span>
        </span>

        {culprit.disk_bytes !== null && culprit.disk_bytes !== undefined && (
          <span style={style('metricLabelValue')}>
            Disk:{" "}
            <span style={highlightData("disk")}>
              {formatBytes(culprit.disk_bytes)}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

/* -----------------------------------
 * MAIN COMPONENT
 * ----------------------------------- */

export default function SpikeDetail() {
  const { id } = useParams();
  const [spike, setSpike] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/spikes/${id}`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);

      const data = await res.json();
      setSpike(data);
    } catch (e) {
      console.error("Spike detail fetch failed:", e);
      setError(`Failed to load spike incident #${id}. Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (error) return <div style={style('errorText')}>API ERROR: {error}</div>;

  if (loading || !spike)
    return <div style={style('loadingText')}>Loading spike #{id} details…</div>;

  const rca = spike.rca || {};
  const culprit = rca.culprit_process || {};
  const impact = rca.resource_impact || {};

  return (
    <div style={style('page')}>
      <header style={style('header')}>
        <Link to="/" style={style('backLink')}>← Return to Dashboard</Link>

        <h1 style={style('title')}>
          <span style={style('titleIcon')}>#</span>
          Incident Spike #{spike.id}
        </h1>

        <p style={style('subtitle')}>
          Detected at: {formatTimestamp(spike.detected_at)}
        </p>
      </header>

      <div style={style('metricGrid')}>
        <Metric
          label="Max CPU %"
          value={
            typeof spike.cpu_at_confirm === "number"
              ? `${spike.cpu_at_confirm.toFixed(1)}%`
              : "?"
          }
          accent={CPU_COLOR}
        />

        <Metric
          label="Max RAM %"
          value={
            typeof spike.ram_at_confirm === "number"
              ? `${spike.ram_at_confirm.toFixed(1)}%`
              : "?"
          }
          accent={RAM_COLOR}
        />

        <Metric
          label="RCA Status"
          value={rca.cause_summary ? "RESOLVED" : "PENDING"}
          accent={rca.cause_summary ? SUCCESS_COLOR : WARNING_COLOR}
        />
      </div>

      <Card title="Root Cause Analysis Summary" icon="🧠">
        <p style={style('bodyText')}>
          {rca.cause_summary || "RCA is currently pending for this spike."}
        </p>

        <p style={style('confidence')}>
          AI Confidence:{" "}
          <strong style={highlightData("confidence")}>
            {typeof rca.confidence === "number"
              ? (rca.confidence * 100).toFixed(1)
              : "0.0"}
            %
          </strong>
        </p>
      </Card>

      {culprit?.pid && (
        <Card title="Primary Culprit Process" highlight icon="💥">
          <CulpritDetails culprit={culprit} />

          {impact?.cpu_spike_percent && (
            <p style={style('mutedText')}>
              Responsible for{" "}
              <span style={highlightData("cpu")}>
                {impact.cpu_spike_percent.toFixed(1)}%
              </span>{" "}
              of the total CPU spike.
            </p>
          )}
        </Card>
      )}

      {Array.isArray(rca.ranked_suspects) && rca.ranked_suspects.length > 0 && (
        <Card title="Ranked Suspects" icon="🕵️">
          <ul style={style('list')}>
            {rca.ranked_suspects.map((p, i) => (
              <li key={`${p.pid}-${i}`}>
                PID {p.pid} – {p.name} (Score:{" "}
                <span style={highlightData("score")}>
                  {typeof p.score === "number" ? p.score.toFixed(3) : "?"}
                </span>
                )
              </li>
            ))}
          </ul>
        </Card>
      )}

      <h2 style={style('rawHeader')}>Raw Telemetry & RCA Data</h2>

      <Card title={`Raw ETW Events (Sample)`} icon="💻">
        <div style={style('eventList')}>
          {(spike.etw_events || []).slice(0, 100).map((ev, idx) => {
            let json = "[Unserializable event]";
            try {
              json = JSON.stringify(ev, null, 2);
            } catch {}
            return (
              <pre key={`${idx}-${ev?.ts || "ev"}`} style={style('eventBlock')}>
                {json}
              </pre>
            );
          })}
        </div>
      </Card>

      <Card title="Full RCA JSON Payload" icon="📄">
        <pre style={style('codeBlock')}>
          {JSON.stringify(spike.rca, null, 2)}
        </pre>
      </Card>
    </div>
  );
}