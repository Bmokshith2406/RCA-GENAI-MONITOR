import json
import os
import time
from pathlib import Path

from google import genai
from jsonschema import validate, ValidationError

# ---------------------------------------------------------
# Gemini setup
# ---------------------------------------------------------

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
client = genai.Client()

SCHEMA_PATH = Path(__file__).parent / "gemini_schema.json"

with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)

TOOLS = [
    {
        "function_declarations": [SCHEMA]
    }
]

# ---------------------------------------------------------
# Helper
# ---------------------------------------------------------

def _safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return default


def _fallback_rca(error: str) -> dict:
    """
    Guaranteed RCA so UI never shows empty state.
    """
    return {
        "cause_summary": f"Automated RCA temporarily unavailable. Reason: {error}",
        "confidence": 0.40,
        "spike_type": "unknown",
        "severity_score": 0.25,
        "resource_impact": {
            "cpu_spike_percent": 0,
            "ram_spike_percent": 0
        },
        "culprit_process": {
            "pid": -1,
            "name": "unknown",
            "cmdline": "",
            "cpu_pct": 0,
            "ram_pct": 0
        },
        "ranked_suspects": [],
        "timeline": [],
        "recs": [
            "Verify Gemini API connectivity.",
            "Inspect prompt schema compatibility.",
            "Retry RCA manually once stability is restored."
        ],
    }


# ---------------------------------------------------------
# RCA ANALYSIS — WITH RETRIES + SAFETY
# ---------------------------------------------------------

def analyze_root_cause(evidence: dict) -> dict:

    print("\n" + "="*80)
    print("🔥 BEGIN GEMINI RCA ANALYSIS")
    print("="*80)

    ranked_lines = []

    for idx, proc in enumerate(
        evidence.get("ranked_pid_candidates", [])[:15], start=1
    ):
        ranked_lines.append(
            f"{idx}. PID {proc.get('pid','N/A')} | "
            f"{proc.get('name','Unknown')} | "
            f"Score={_safe_float(proc.get('final_score')):.4f} | "
            f"CPU={_safe_float(proc.get('cpu_pct')):.2f}% | "
            f"RAM={_safe_float(proc.get('ram_pct')):.2f}% | "
            f"Events={int(_safe_float(proc.get('event_rate')))} | "
            f"Threads={int(_safe_float(proc.get('thread_rate')))} | "
            f"NetBytes={int(_safe_float(proc.get('net_bytes')))} | "
            f"DiskBytes={int(_safe_float(proc.get('disk_bytes')))}"
        )

    ranked_block = "\n".join(ranked_lines) if ranked_lines else \
        "No ranked PID candidates available."


    evidence_summary_str = f"""
* **Collected At:** {evidence.get("collected_at", "N/A")}
* **Spike Type:** {evidence.get('spike_info',{}).get('spike_type','unknown')}
* **Severity Score:** {_safe_float(evidence.get('spike_info',{}).get('severity_score')):.2f}
* **CPU at Spike Confirmation:** {_safe_float(evidence.get("cpu_at_confirm")):.1f}%
* **RAM at Spike Confirmation:** {_safe_float(evidence.get("ram_at_confirm")):.1f}%
* **Context Switch Rate:** {_safe_float(evidence.get("cpu_contention",{}).get("context_switch_rate"))}
* **GC Events (window):** {_safe_float(evidence.get("gc_event_count"))}
* **Page Fault Events:** {_safe_float(evidence.get("page_fault_event_count"))}
* **Total ETW Events Analyzed:** {int(_safe_float(evidence.get("etw_events_count")))}

---

### Network Usage
{json.dumps(evidence.get("network_usage_top_pids",{}), indent=2)}

### Disk Usage
{json.dumps(evidence.get("disk_usage_top_pids",{}), indent=2)}

### Thread Spikes
{json.dumps(evidence.get("thread_spikes",{}), indent=2)}

### Ranked Candidate Processes
{ranked_block}
"""

    prompt = f"""
You are a **Windows Server Root Cause Analysis AI – DIAGNOSTIC MODE**.

Return **ONLY** a function call to:
"{SCHEMA['name']}"

Output must match the schema EXACTLY.

{evidence_summary_str}
"""

    # ---------------------------------------------------------
    # RETRY CONFIG
    # ---------------------------------------------------------

    MAX_RETRIES = 3
    BASE_DELAY = 2.0

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(f"\n🚀 Gemini request attempt {attempt}/{MAX_RETRIES}")

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"tools": TOOLS}
            )

            print("\n📥 RAW GEMINI RESPONSE:")
            print("-"*80)
            print(response)
            print("-"*80)

            # ---------------------------------------------------------
            # Parse Function Call
            # ---------------------------------------------------------
            try:
                function_call = response.candidates[0].content.parts[0].function_call
                raw_json = function_call.args
            except Exception:
                raw_json = json.loads(response.text)

            print("\n✅ FUNCTION CALL ARGS RECEIVED:")
            print(json.dumps(raw_json, indent=2))

            # ---------------------------------------------------------
            # Schema validation
            # ---------------------------------------------------------
            validate(instance=raw_json, schema=SCHEMA)

            print("\n✅ SCHEMA VALIDATION PASSED")
            last_error = None

            break

        except ValidationError as e:
            last_error = f"Schema validation error: {e.message}"
            print("❌", last_error)

        except Exception as e:
            last_error = str(e)
            print("❌ Gemini error:", last_error)

        # ---------------------------------------------------------
        # Retry backoff
        # ---------------------------------------------------------
        if attempt < MAX_RETRIES:
            delay = BASE_DELAY * (2 ** (attempt - 1))
            print(f"⏳ Retrying in {delay:.1f}s...\n")
            time.sleep(delay)

        else:
            print("\n🚨 Gemini RCA FAILED after max retries.")


    # ---------------------------------------------------------
    # Final fallback if everything failed
    # ---------------------------------------------------------
    if last_error:
        print("\n⚠ FALLBACK RCA RETURNED")
        return _fallback_rca(last_error)

    # ---------------------------------------------------------
    # POST SAFETY NORMALIZATION
    # ---------------------------------------------------------

    raw_json["confidence"] = round(
        min(max(_safe_float(raw_json.get("confidence", 0.7)), 0.4), 0.95),
        2
    )

    impact = raw_json.get("resource_impact", {})
    ram_pct = _safe_float(impact.get("ram_spike_percent"))

    if ram_pct > 70:
        sev = 0.8
    elif ram_pct > 50:
        sev = 0.5
    else:
        sev = 0.25

    raw_json["severity_score"] = round(max(
        _safe_float(raw_json.get("severity_score"), sev),
        sev
    ), 2)

    recs = raw_json.get("recs", [])
    if not isinstance(recs, list) or len(recs) < 3:
        raw_json["recs"] = [
            "Investigate memory usage of top-ranked processes.",
            "Apply resource limits or scheduling constraints.",
            "Improve alert-response workflows."
        ]

    print("\n🎉 RCA SUCCESSFULLY GENERATED")
    print("="*80 + "\n")

    return raw_json
