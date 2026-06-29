"""
consumer/parser.py  (Phase 3 — instrumented)
─────────────────────────────────────────────
parse stage SLO budget: 80 ms
Wraps the core parse logic with @timed_stage("parse") so every call is
automatically timed and checked against the budget.
"""

import re
import time
from datetime import datetime, timezone
from typing import Optional

from monitoring.slo import timed_stage

# ── Regex patterns ────────────────────────────────────────────────────────
_TIMESTAMP_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_LEVEL_RE = re.compile(
    r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE
)
_SERVICE_RE = re.compile(r"\b(service|app|svc)[=: ]+(\S+)", re.IGNORECASE)
_TRACE_RE = re.compile(r"trace[_-]?id[=: ]+([a-f0-9\-]{8,})", re.IGNORECASE)
_REQUEST_ID_RE = re.compile(r"request[_-]?id[=: ]+([a-f0-9\-]{8,})", re.IGNORECASE)


def _normalise_level(raw: str) -> str:
    upper = raw.upper()
    if upper in ("WARNING",):
        return "WARN"
    if upper in ("FATAL",):
        return "CRITICAL"
    return upper


@timed_stage("parse")
def parse_log(raw: str) -> Optional[dict]:
    """
    Parse a raw log string into a structured dict.
    Returns None if the minimum required fields cannot be extracted.

    Decorated with @timed_stage("parse") — automatically records:
      • rtla_stage_latency_seconds{stage="parse"}
      • rtla_slo_violations_total{stage="parse"}  (when > 80 ms)
    """
    if not raw or not raw.strip():
        return None

    result: dict = {"raw": raw.strip()}

    # Timestamp
    ts_match = _TIMESTAMP_RE.search(raw)
    if ts_match:
        try:
            ts_str = ts_match.group(1).replace(" ", "T")
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            result["timestamp"] = datetime.fromisoformat(ts_str).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            result["timestamp"] = datetime.now(timezone.utc)
    else:
        result["timestamp"] = datetime.now(timezone.utc)

    # Level
    level_match = _LEVEL_RE.search(raw)
    result["level"] = _normalise_level(level_match.group(1)) if level_match else "INFO"

    # Service
    svc_match = _SERVICE_RE.search(raw)
    result["service"] = svc_match.group(2) if svc_match else "unknown"

    # Trace / request IDs
    trace_match = _TRACE_RE.search(raw)
    result["trace_id"] = trace_match.group(1) if trace_match else None

    req_match = _REQUEST_ID_RE.search(raw)
    result["request_id"] = req_match.group(1) if req_match else None

    # Message body: everything after the level token
    if level_match:
        body_start = level_match.end()
        result["message"] = raw[body_start:].strip(" :-|")
    else:
        result["message"] = raw.strip()

    result["parse_latency_ms"] = None   # filled in by the timed_stage wrapper externally if needed

    return result