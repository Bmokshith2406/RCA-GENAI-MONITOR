import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";

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
  if (!bytes && bytes !== 0) return "—";
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
    <div style={{ ...metricStyle, borderLeftColor: accent }}>
      <span style={metricLabelStyle}>{label}</span>
      <strong style={{ ...metricValueStyle, color: accent }}>{value}</strong>
    </div>
  );
}

function Card({ title, children, highlight, icon }) {
  return (
    <section
      style={{
        ...cardStyle,
        borderLeftColor: highlight ? PRIMARY_COLOR : BORDER_COLOR,
        background: highlight ? `${BASE_BG}e6` : CARD_BG,
        padding: title === "Raw ETW Events" ? "0" : "1.5rem",
      }}
    >
      <h3 style={cardTitleStyle}>
        <span style={cardTitleIcon}>{icon}</span>
        {title}
      </h3>
      <div style={cardContentStyle(title)}>{children}</div>
    </section>
  );
}

function CulpritDetails({ culprit }) {
  if (!culprit || !culprit.pid) return null;

  return (
    <div style={culpritContainerStyle}>
      <div style={culpritHeaderStyle}>
        <strong style={culpritNameStyle}>{culprit.name}</strong>
        <span style={mutedTextStyle}>(PID {culprit.pid})</span>
      </div>

      {culprit.cmdline && <p style={cmdTextStyle}>{culprit.cmdline}</p>}

      <div style={culpritMetricsStyle}>
        <span style={metricLabelValueStyle}>
          CPU: <span style={highlightData("cpu")}>{culprit.cpu_pct?.toFixed(1) || "?"}%</span>
        </span>

        <span style={metricLabelValueStyle}>
          RAM: <span style={highlightData("ram")}>{culprit.ram_pct?.toFixed(1) || "?"}%</span>
        </span>

        {culprit.disk_bytes && (
          <span style={metricLabelValueStyle}>
            Disk: <span style={highlightData("disk")}>{formatBytes(culprit.disk_bytes)}</span>
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
      if (!res.ok) throw new Error(`HTTP error! Status: ${res.status}`);
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

  if (error)
    return <div style={errorTextStyle}>API ERROR: {error}</div>;

  if (loading || !spike)
    return <div style={loadingTextStyle}>Loading incident spike #{id} data…</div>;

  const rca = spike.rca || {};
  const culprit = rca.culprit_process || {};
  const impact = rca.resource_impact || {};

  return (
    <div style={pageStyle}>
      <header style={headerStyle}>
        <Link to="/" style={backLinkStyle}>
          ← Return to Dashboard
        </Link>

        <h1 style={titleStyle}>
          <span style={titleIconStyle}>💥</span>
          Incident Spike #{spike.id}
        </h1>

        <p style={subtitleStyle}>
          Detected at: {formatTimestamp(spike.detected_at)}
        </p>
      </header>

      {/* KEY METRICS */}
      <div style={metricGridStyle}>
        <Metric
          label="Max CPU %"
          value={`${spike.cpu_at_confirm?.toFixed?.(1) || "?"}%`}
          accent={CPU_COLOR}
        />
        <Metric
          label="Max RAM %"
          value={`${spike.ram_at_confirm?.toFixed?.(1) || "?"}%`}
          accent={RAM_COLOR}
        />
        <Metric
          label="RCA Status"
          value={rca.cause_summary ? "RESOLVED" : "PENDING"}
          accent={rca.cause_summary ? SUCCESS_COLOR : WARNING_COLOR}
        />
      </div>

      {/* RCA SUMMARY */}
      <Card title="Root Cause Analysis Summary" icon="🧠">
        <p style={bodyTextStyle}>
          {rca.cause_summary || "RCA is currently pending for this spike."}
        </p>

        <p style={confidenceStyle}>
          AI Confidence:{" "}
          <strong style={highlightData("confidence")}>
            {typeof rca.confidence === "number"
              ? (rca.confidence * 100).toFixed(1)
              : "0.0"}
            %
          </strong>
        </p>
      </Card>

      {/* PRIMARY CULPRIT */}
      {culprit?.pid && (
        <Card title="Primary Culprit Process" highlight icon="🔥">
          <CulpritDetails culprit={culprit} />

          {impact?.cpu_spike_percent && (
            <p style={mutedTextStyle}>
              This process was responsible for{" "}
              <span style={highlightData("cpu")}>
                {impact.cpu_spike_percent.toFixed(1)}%
              </span>{" "}
              of the total CPU spike.
            </p>
          )}
        </Card>
      )}

      {/* RANKED SUSPECTS */}
      {Array.isArray(rca.ranked_suspects) &&
        rca.ranked_suspects.length > 0 && (
          <Card title="Ranked Suspects" icon="🕵️">
            <ul style={listStyle}>
              {rca.ranked_suspects.map((p, i) => (
                <li key={i}>
                  PID {p.pid} – {p.name} (Score:{" "}
                  <span style={highlightData("score")}>
                    {typeof p.score === "number"
                      ? p.score.toFixed(3)
                      : "?"}
                  </span>
                  )
                </li>
              ))}
            </ul>
          </Card>
        )}

      {/* NETWORK CONTEXT */}
      {rca.net_context?.top_connections?.length > 0 && (
        <Card title="Top Network Activity Context" icon="🌐">
          <div style={networkListStyle}>
            {rca.net_context.top_connections.map((c, i) => (
              <div key={i} style={netRowStyle}>
                <span style={netArrowStyle}>→</span>
                <strong style={netPidStyle}>PID {c.pid ?? "?"}</strong>

                <span style={netTargetStyle}>
                  {c.daddr}
                  {c.dport ? `:${c.dport}` : ""}
                </span>

                {typeof c.bytes_transferred === "number" && (
                  <span style={netBytesStyle}>
                    ({formatBytes(c.bytes_transferred)} transferred)
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* TIMELINE */}
      {Array.isArray(rca.timeline) &&
        rca.timeline.length > 0 && (
          <Card
            title={`Spike Event Timeline (${rca.timeline.length} events)`}
            icon="🕰️"
          >
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle, minWidth: "100px" }}>
                      Time
                    </th>
                    <th style={thStyle}>Event Type</th>
                    <th style={{ ...thStyle, minWidth: "300px" }}>
                      Details / Reason
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {rca.timeline.map((t, i) => (
                    <tr key={i} style={rowStyle}>
                      <td style={tdMonoStyle}>{t.ts}</td>
                      <td style={tdStyle}>{t.event_type}</td>
                      <td style={tdStyle}>
                        {t.details || t.reason || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

      {/* RAW DATA */}
      <h2 style={rawHeaderStyle}>
        Raw Telemetry and Analysis Data
      </h2>

      <Card
        title={`Raw ETW Events Sample (First 100 of ${
          spike.etw_events?.length || 0
        })`}
        icon="💻"
      >
        <div style={eventListStyle}>
          {(spike.etw_events || []).slice(0, 100).map((ev, idx) => (
            <pre key={idx} style={eventBlockStyle}>
              {JSON.stringify(ev, null, 2)}
            </pre>
          ))}
        </div>
      </Card>

      <Card title="Full RCA JSON Payload" icon="📄">
        <pre style={codeBlockStyle}>
          {JSON.stringify(spike.rca, null, 2)}
        </pre>
      </Card>
    </div>
  );
}

/* ===================== STYLES ===================== */

/* Deloitte Green Theme */
const PRIMARY_COLOR = "#43B02A";
const SECONDARY_COLOR = "#9CA3AF";
const SUCCESS_COLOR = "#43B02A";
const WARNING_COLOR = "#FACC15";

const CPU_COLOR = "#16A34A";
const RAM_COLOR = "#22C55E";
const DISK_COLOR = "#4ADE80";

const BASE_BG = "#000000";
const CARD_BG = "#0B0F0C";
const BORDER_COLOR = "#1F2937";

/* Layout */
const pageStyle = {
  background: BASE_BG,
  minHeight: "100vh",
  padding: "2.5rem",
  color: "#E5E7EB",
  fontFamily: "Inter, system-ui, sans-serif",
};

const headerStyle = {
  marginBottom: "2rem",
  borderBottom: `1px solid ${BORDER_COLOR}`,
  paddingBottom: "1rem",
};

const titleStyle = {
  fontSize: "2rem",
  marginTop: "0.5rem",
  display: "flex",
  alignItems: "center",
};

const titleIconStyle = {
  marginRight: "10px",
  color: PRIMARY_COLOR,
  fontSize: "1.8rem",
};

const subtitleStyle = {
  color: SECONDARY_COLOR,
  marginTop: "0.3rem",
};

const backLinkStyle = {
  color: PRIMARY_COLOR,
  textDecoration: "none",
  fontSize: "0.85rem",
  fontWeight: 600,
};

/* Metrics */
const metricGridStyle = {
  display: "grid",
  gap: "1.5rem",
  gridTemplateColumns: "repeat(3, 1fr)",
  marginBottom: "2rem",
};

const metricStyle = {
  background: CARD_BG,
  borderLeft: "5px solid",
  borderRadius: "8px",
  padding: "1rem 1.25rem",
};

const metricLabelStyle = {
  color: SECONDARY_COLOR,
  fontSize: "0.8rem",
  textTransform: "uppercase",
};

const metricValueStyle = {
  fontSize: "1.75rem",
  fontWeight: 700,
};

/* Cards */
const cardStyle = {
  background: CARD_BG,
  borderLeft: `5px solid ${BORDER_COLOR}`,
  borderRadius: "12px",
  marginBottom: "1.5rem",
};

const cardTitleStyle = {
  fontSize: "1.15rem",
  fontWeight: 700,
  marginBottom: "1rem",
  borderBottom: `1px dashed ${BORDER_COLOR}`,
  display: "flex",
  alignItems: "center",
  paddingBottom: "0.75rem",
};

const cardTitleIcon = {
  marginRight: "8px",
  color: PRIMARY_COLOR,
};

const cardContentStyle = () => ({
  paddingTop: "0.5rem",
});

/* Text */
const bodyTextStyle = { color: "#E5E7EB" };
const confidenceStyle = { color: SUCCESS_COLOR, marginTop: "1rem" };
const mutedTextStyle = { color: SECONDARY_COLOR };
const listStyle = { paddingLeft: "1.25rem" };

/* Culprit */
const culpritContainerStyle = {
  background: BASE_BG,
  borderRadius: "6px",
  padding: "1rem",
  border: `1px solid ${PRIMARY_COLOR}40`,
};

const culpritHeaderStyle = {
  display: "flex",
  gap: "8px",
};

const culpritNameStyle = {
  fontSize: "1.1rem",
  color: "#ffffff",
};

const culpritMetricsStyle = {
  display: "flex",
  gap: "1.5rem",
  marginTop: "0.75rem",
};

const metricLabelValueStyle = {
  fontSize: "0.9rem",
  color: SECONDARY_COLOR,
};

const cmdTextStyle = {
  color: SECONDARY_COLOR,
  fontSize: "0.75rem",
  fontFamily: "monospace",
};

const highlightData = type => ({
  color:
    type === "cpu"
      ? CPU_COLOR
      : type === "ram"
      ? RAM_COLOR
      : type === "disk"
      ? DISK_COLOR
      : type === "confidence"
      ? SUCCESS_COLOR
      : type === "score"
      ? WARNING_COLOR
      : PRIMARY_COLOR,
  fontWeight: 700,
});

/* Network */
const networkListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const netRowStyle = {
  background: BASE_BG,
  borderLeft: `3px solid ${PRIMARY_COLOR}`,
  padding: "6px 10px",
  borderRadius: "4px",
  display: "flex",
  gap: "8px",
  fontFamily: "monospace",
};

const netArrowStyle = { color: PRIMARY_COLOR };
const netPidStyle = { color: WARNING_COLOR };
const netTargetStyle = {
  color: SUCCESS_COLOR,
  flexGrow: 1,
};

const netBytesStyle = {
  color: SECONDARY_COLOR,
  fontSize: "0.75rem",
};

/* Table */
const tableWrapStyle = {
  maxHeight: "350px",
  overflowY: "auto",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
};

const thStyle = {
  color: SECONDARY_COLOR,
  borderBottom: `1px solid ${BORDER_COLOR}`,
  padding: "0.5rem 0",
  textTransform: "uppercase",
};

const tdStyle = {
  padding: "0.75rem 0",
  borderBottom: `1px dashed ${BORDER_COLOR}60`,
};

const tdMonoStyle = {
  ...tdStyle,
  fontFamily: "monospace",
  color: PRIMARY_COLOR,
};

const rowStyle = {};

/* Raw Data */
const rawHeaderStyle = {
  color: PRIMARY_COLOR,
  marginTop: "2.5rem",
};

const eventListStyle = {
  maxHeight: "30vh",
  overflowY: "auto",
};

const eventBlockStyle = {
  background: BASE_BG,
  padding: "0.75rem 1.5rem",
  borderBottom: `1px solid ${BORDER_COLOR}`,
  fontSize: "0.65rem",
  color: SECONDARY_COLOR,
  fontFamily: "monospace",
};

const codeBlockStyle = {
  background: BASE_BG,
  border: `1px dashed ${BORDER_COLOR}`,
  padding: "1.25rem",
  fontSize: "0.75rem",
  overflowX: "auto",
};

/* States */
const errorTextStyle = {
  color: "#EF4444",
  padding: "2rem",
  background: CARD_BG,
};

const loadingTextStyle = {
  color: PRIMARY_COLOR,
  padding: "2rem",
  background: CARD_BG,
};
