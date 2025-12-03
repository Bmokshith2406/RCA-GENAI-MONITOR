import React, { useEffect, useState, useRef, useCallback } from "react";

/* -----------------------------------
 * HELPER FUNCTIONS
 * ----------------------------------- */

function formatEvent(event) {
  const rawTimestamp = event.ts;
  let timeLabel = rawTimestamp;

  if (rawTimestamp) {
    const date = new Date(rawTimestamp);
    if (!isNaN(date.getTime())) {
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
      timeLabel = `${dateOnly} ${timeOnly}`;
    }
  }

  const id = `${rawTimestamp}-${event.pid}-${event.tid}-${event.event_type || event.eventType}`;

  return {
    id,
    time: timeLabel,
    event_type: event.event_type || event.eventType || "unknown",
    provider: event.provider || "kernel",
    pid: event.pid,
    tid: event.tid,
    cpu_core: event.cpu ?? null,
    net_bytes: event.net_bytes ?? null,
    disk_bytes: event.disk_bytes ?? null,
    reason: event.reason ?? null,
    payload: event.payload ?? undefined,
  };
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
 * MAIN COMPONENT
 * ----------------------------------- */

export default function LiveEvents() {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [isPaused, setIsPaused] = useState(false);
  const listRef = useRef(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch("/api/events?limit=250");
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      setEvents(prev => {
        const newOnes = (data.events || []).filter(e =>
          !prev.some(p => p.ts === e.ts && p.pid === e.pid)
        );

        const combined = [...newOnes, ...prev];
        return combined.slice(0, 500);
      });

      setError(null);
    } catch (err) {
      console.error("Live event fetch failed", err);
      setError(`Failed to fetch events: ${err.message}`);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    const poll = setInterval(fetchEvents, 1000);
    return () => clearInterval(poll);
  }, [fetchEvents]);

  useEffect(() => {
    if (listRef.current && !isPaused) listRef.current.scrollTop = 0;
  }, [events, isPaused]);

  const togglePause = () => setIsPaused(p => !p);
  const clearEvents = () => setEvents([]);

  return (
    <div style={panel}>
      {/* HEADER */}
      <header style={panelHeader}>
        <h2 style={title}>
          <span style={titleIcon}>⚡</span>
          Live Kernel Events ({events.length})
        </h2>

        <div style={controls}>
          <button onClick={togglePause} style={button(isPaused)}>
            {isPaused ? "▶ Resume" : "⏸ Pause"}
          </button>

          <button onClick={clearEvents} style={button(false, "danger")}>
            🗑 Clear
          </button>

          <span style={liveBadge}>
            <span style={pulseDot} />
            {isPaused ? "PAUSED" : "STREAMING"}
          </span>
        </div>
      </header>

      {/* ERROR */}
      {error && <div style={errorBanner}>{error}</div>}

      {/* LIST */}
      <div style={list} ref={listRef}>
        {events.length === 0 && !error ? (
          <div style={emptyState}>Awaiting first events...</div>
        ) : (
          events.map(raw => {
            const ev = formatEvent(raw);
            return <EventRow key={ev.id} ev={ev} />;
          })
        )}
      </div>
    </div>
  );
}

/* -----------------------------------
 * EVENT ROW
 * ----------------------------------- */

function EventRow({ ev }) {
  const [showPayload, setShowPayload] = useState(false);

  return (
    <div
      style={row}
      onClick={() => ev.payload && setShowPayload(p => !p)}
    >
      <div style={time}>{ev.time}</div>

      <div style={badgeStyle(ev.event_type)}>
        {ev.event_type.toUpperCase()}
      </div>

      <div style={providerStyle}>{ev.provider}</div>

      <div style={pidStyle}>
        PID:{ev.pid ?? "?"} · TID:{ev.tid ?? "?"}
      </div>

      <div style={metricStyle}>
        {ev.cpu_core !== null ? `CPU ${ev.cpu_core}` : <span style={mutedStyle}>N/A</span>}
      </div>

      <div style={metricStyle}>
        {ev.net_bytes !== null ? `NET ${formatBytes(ev.net_bytes)}` : <span style={mutedStyle}>—</span>}
      </div>

      <div style={metricStyle}>
        {ev.disk_bytes !== null ? `DISK ${formatBytes(ev.disk_bytes)}` : <span style={mutedStyle}>—</span>}
      </div>

      {ev.reason && <div style={reasonStyle}>{ev.reason}</div>}

      {ev.payload && showPayload && (
        <pre style={payloadStyle}>
          {JSON.stringify(ev.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

/* ===========================
            STYLES
=========================== */

/* Deloitte Theme */
const PRIMARY_COLOR = "#43B02A";
const SUCCESS_COLOR = "#22C55E";
const WARNING_COLOR = "#FACC15";
const DANGER_COLOR = "#DC2626";

const BASE_BG = "#000000";
const DARKER_BG = "#0B0F0C";
const TEXT_LIGHT = "#E5E7EB";
const TEXT_MUTED = "#9CA3AF";

/* Layout */
const panel = {
  marginTop: "2rem",
  background: BASE_BG,
  border: `1px solid ${DARKER_BG}`,
  borderRadius: "12px",
  padding: "1.5rem",
  boxShadow: "0 20px 50px rgba(0,0,0,0.8)",
  fontFamily: "Inter, system-ui, sans-serif",
};

const panelHeader = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "1rem",
  borderBottom: `1px solid ${DARKER_BG}`,
  paddingBottom: "1rem",
};

const title = {
  fontSize: "1.25rem",
  fontWeight: 700,
  color: TEXT_LIGHT,
  display: "flex",
  alignItems: "center",
};

const titleIcon = {
  marginRight: "8px",
};

const controls = {
  display: "flex",
  gap: "10px",
  alignItems: "center",
};

const button = (isActive, type = "default") => ({
  padding: "6px 12px",
  borderRadius: "6px",
  fontSize: "0.75rem",
  fontWeight: 600,
  cursor: "pointer",
  border: `1px solid ${type === "danger" ? DANGER_COLOR : PRIMARY_COLOR}`,
  background:
    isActive
      ? PRIMARY_COLOR
      : type === "danger"
      ? DANGER_COLOR
      : BASE_BG,
  color:
    isActive || type === "danger" ? TEXT_LIGHT : PRIMARY_COLOR,
});

const liveBadge = {
  background: SUCCESS_COLOR + "22",
  color: SUCCESS_COLOR,
  padding: "4px 10px",
  borderRadius: "999px",
  fontSize: "0.65rem",
  letterSpacing: "0.05em",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
};

const pulseDot = {
  height: "8px",
  width: "8px",
  marginRight: "6px",
  backgroundColor: SUCCESS_COLOR,
  borderRadius: "50%",
};

const errorBanner = {
  background: DANGER_COLOR + "22",
  color: DANGER_COLOR,
  padding: "10px 15px",
  borderRadius: "6px",
  marginBottom: "1rem",
  fontSize: "0.85rem",
  fontWeight: 600,
  border: `1px solid ${DANGER_COLOR}`,
};

const list = {
  maxHeight: "450px",
  overflowY: "scroll",
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  direction: "rtl",
};

const row = {
  direction: "ltr",
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "1rem",
  background: DARKER_BG,
  padding: "0.75rem 1rem",
  borderRadius: "8px",
  borderLeft: `3px solid ${PRIMARY_COLOR}`,
};

const time = {
  minWidth: "120px",
  fontFamily: "monospace",
  fontSize: "0.8rem",
  color: TEXT_MUTED,
};

const badgeStyle = type => ({
  background:
    type === "process"
      ? PRIMARY_COLOR + "22"
      : type === "network"
      ? SUCCESS_COLOR + "22"
      : type === "disk"
      ? DANGER_COLOR + "22"
      : WARNING_COLOR + "22",

  color:
    type === "process"
      ? PRIMARY_COLOR
      : type === "network"
      ? SUCCESS_COLOR
      : type === "disk"
      ? DANGER_COLOR
      : WARNING_COLOR,

  borderRadius: "4px",
  padding: "3px 8px",
  fontSize: "0.65rem",
  textTransform: "uppercase",
  fontWeight: 700,
  minWidth: "70px",
  textAlign: "center",
});

const providerStyle = {
  fontSize: "0.75rem",
  color: TEXT_MUTED,
  minWidth: "70px",
};

const pidStyle = {
  fontSize: "0.75rem",
  minWidth: "110px",
  color: TEXT_LIGHT,
  fontFamily: "monospace",
};

const metricStyle = {
  fontSize: "0.75rem",
  minWidth: "85px",
  color: TEXT_LIGHT,
  fontWeight: 500,
};

const mutedStyle = {
  color: TEXT_MUTED,
};

const reasonStyle = {
  fontSize: "0.7rem",
  color: WARNING_COLOR,
  background: WARNING_COLOR + "22",
  borderRadius: "4px",
  padding: "3px 8px",
  maxWidth: "200px",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  fontWeight: 600,
};

const payloadStyle = {
  width: "100%",
  marginTop: "0.75rem",
  fontSize: "0.7rem",
  fontFamily: "monospace",
  color: TEXT_MUTED,
  background: BASE_BG,
  border: `1px dashed ${TEXT_MUTED + "44"}`,
  borderRadius: "6px",
  padding: "10px",
  maxWidth: "100%",
  overflowX: "auto",
};

const emptyState = {
  padding: "2rem",
  textAlign: "center",
  color: TEXT_MUTED,
  fontSize: "1rem",
};
