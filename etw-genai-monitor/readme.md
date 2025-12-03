# ETW-GenAI Monitor  
### Real-Time Causal Inference & Automated Root Cause Analysis for Windows Performance

---

## Overview

**ETW-GenAI Monitor** is a real-time performance diagnostics and **automated Root Cause Analysis (RCA)** platform for Microsoft Windows built on top of low-level **Event Tracing for Windows (ETW)** telemetry and advanced **multivariate causal inference algorithms**.

Traditional monitoring tools report only symptoms (CPU/RAM alarms). ETW-GenAI Monitor instead identifies the **true causal processes** responsible for performance regression and automatically produces a **human-readable RCA report** using **Google Gemini LLMs**.

The goal is simple:

> Provide statistically proven explanations of **why** an incident occurred — not just that it happened.

---

## Key Capabilities

### Real-Time Bottleneck Detection
- Continuous kernel-level telemetry capture via ETW.
- Rolling statistical baselines over CPU & memory metrics.
- Spike detection based on:
  - Robust Z-scores.
  - Trend derivatives and persistence filtering.

---

### Causal Inference Engine

For each detected incident window, multivariate analysis is applied:

- **Anomaly Detection**
  - Robust Z-score analysis.
  - Mahalanobis distance across correlated metrics.

- **Energy Contribution Attribution**
  - Calculates each PID’s proportional resource usage relative to the entire system spike.

- **Temporal Correlation**
  - Cosine similarity comparison between each PID’s activity curve and the global spike profile.

The final causal confidence score:

\[
\text{FinalScore}
= 0.4 \times \text{Anomaly}
+ 0.4 \times \text{Energy}
+ 0.2 \times \text{Correlation}
\]

Processes are ranked by this score to identify the most probable **root cause PID**.

---

### Automated RCA via Gemini AI

- Structured evidence payload is forwarded to **Gemini 2.5 Flash**.
- Generates professional RCA sections:
  - Incident summary.
  - Causal explanation.
  - Impact assessment.
  - Remediation recommendations.

These reports are stored and surfaced live in the dashboard.

---

### Web Dashboard

- React-based frontend.
- Real-time visualization:
  - System spike graphs.
  - Ranked PID tables.
  - RCA report output.
- Powered by REST APIs from the FastAPI backend.

---

---

## System Scope

### In Scope

- Windows ETW kernel telemetry ingestion.
- Process-level metric aggregation.
- Real-time spike detection.
- Statistical causal ranking.
- Automated RCA generation using Gemini.
- Live visualization dashboard.

---

### Explicitly Out of Scope

- Automated remediation or self-healing actions.
- Kernel or driver modification.
- Deep hardware telemetry beyond standard OS APIs (e.g., discrete GPU VRAM).
- Deployment orchestration or system configuration management.

The system is **read-only**, passive, and **does not alter system state**.

---

---

## High-Level Architecture

```text
┌───────────────────┐
│ Windows Kernel   │
│ ETW Events       │
└─────────┬─────────┘
          │
          ▼
┌────────────────────┐
│ C# ETW Tracer      │
│ (.NET Kernel Hook)│
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Python Stream      │
│ Collector Layer   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Spike Detector     │
│ (Z-score + Trends)│
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ PID Ranker         │
│ - Mahalanobis     │
│ - Energy Modeling │
│ - Correlation     │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Gemini RCA Client  │
│ (LLM Generator)   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ FastAPI Backend    │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ React Dashboard    │
└────────────────────┘
````

---

---

## Technology Stack

### Backend

* Python 3.10+
* NumPy, SciPy
* FastAPI
* Uvicorn

### Tracing Layer

* C# (.NET 8.0)
* Microsoft.Diagnostics.Tracing

### Frontend

* React
* Vite

### AI Layer

* Google Gemini 2.5 Flash

---

---

## System Requirements

### Supported Operating System

* Windows 10 or Windows 11 (x64 only)

### Dependency Matrix

| Component                  | Version          |
| -------------------------- | ---------------- |
| Python                     | 3.10+            |
| .NET SDK                   | 8.0 (x64)        |
| Node.js                    | LTS              |
| Java SDK                   | Latest           |
| Visual C++ Redistributable | Latest           |
| Gemini API Key             | Gemini 2.5 Flash |

---

---

## One-Time Setup

### Build the Kernel ETW Tracer

```powershell
cd windows/EtwKernelTracer
dotnet restore
dotnet build -c Release
```

---

### Setup Python Runtime

```powershell
cd etw-genai-monitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

### Configure Gemini API Access

```powershell
set GOOGLE_API_KEY="YOUR_API_KEY_HERE"
```

---

---

## Running The System

### Start Backend (Administrator Required)

```powershell
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

> Administrator permissions are mandatory since kernel ETW providers require elevated privileges.

---

---

### Start React Dashboard

```powershell
cd dashboard
npm install
npm run dev
```

---

---

### Open Dashboard

Open your browser and navigate to:

```text
http://localhost:5173
```

---

---

## Runtime Flow

1. Kernel ETW events stream continuously into the tracer.
2. Python backend processes metrics in near-real time.
3. Spike detector checks metrics against rolling baselines.
4. Upon sustained spike detection:

   * PID Ranker aggregates telemetry.
   * Multivariate statistical scoring applied.
   * Highest ranked PID marked as causal agent.
5. Evidence payload sent to Gemini.
6. LLM generates RCA report.
7. Dashboard updates instantly with findings.

---

---

## Security and Permissions

* Backend must be executed as **Administrator**.
* No system settings or kernel behaviors are modified.
* No outbound telemetry except structured RCA prompts to Gemini.
* No personal or user-identifiable data collection.

---

---

## Design Philosophy

Core principles of the system:

* Evidence-first observability.
* Mathematical causality over static thresholds.
* Transparent RCA output designed for engineers.
* 100% non-invasive monitoring.

This design transitions operations from **metric watching** to **automated root-cause reasoning**.


