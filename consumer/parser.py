"""
RTLA Phase 1 — Log Parser
Parses raw log strings into structured dicts.
Measures parse latency per entry (feeds into Phase 3 SLOs).
"""

import re
import time
import json
from datetime import datetime
from typing import Optional

# ── Regex patterns (ordered by specificity) ──────────────────────────────────

_PATTERNS = [
    # Standard:  2024-01-15 14:32:01 ERROR service-name: message
    re.compile(
        r"(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)"
        r"\s+(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL)"
        r"\s+(?P<service>[\w\-\.]+)"
        r":\s*(?P<message>.+)"
    ),
    # Bracket:   [2024-01-15 14:32:01] [ERROR] service - message
    re.compile(
        r"\[(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})\]"
        r"\s+\[(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL)\]"
        r"\s+(?P<service>[\w\-\.]+)"
        r"\s+-\s+(?P<message>.+)"
    ),
]

_LEVEL_NORMALISE = {
    "WARNING":  "WARN",
    "CRITICAL": "ERROR",
}

_TS_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S,%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
]

VALID_LEVELS = {"ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"}


# ── Public API ────────────────────────────────────────────────────────────────

def parse_log(raw: str) -> Optional[dict]:
    """
    Parse a raw log string into a structured dict.
    Returns None only if the input is blank.
    Always returns something otherwise (fallback to UNKNOWN level).
    """
    t0 = time.perf_counter()
    raw = raw.strip()
    if not raw:
        return None

    entry = _try_json(raw) or _try_regex(raw) or _fallback(raw)
    entry["parse_latency_ms"] = round((time.perf_counter() - t0) * 1000, 4)
    return entry


# ── Private helpers ───────────────────────────────────────────────────────────

def _try_json(raw: str) -> Optional[dict]:
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
        ts_str  = data.get("timestamp") or data.get("time") or data.get("@timestamp") or ""
        level   = _norm_level(str(data.get("level", data.get("severity", "INFO"))))
        service = str(data.get("service", data.get("logger", "unknown")))
        message = str(data.get("message", data.get("msg", raw)))
        return {
            "timestamp": _parse_ts(ts_str),
            "level":     level,
            "service":   service,
            "message":   message[:2000],
            "raw":       raw,
        }
    except Exception:
        return None


def _try_regex(raw: str) -> Optional[dict]:
    for pattern in _PATTERNS:
        m = pattern.match(raw)
        if m:
            return {
                "timestamp": _parse_ts(m.group("timestamp")),
                "level":     _norm_level(m.group("level")),
                "service":   m.group("service"),
                "message":   m.group("message").strip()[:2000],
                "raw":       raw,
            }
    return None


def _fallback(raw: str) -> dict:
    """Store unparseable logs so nothing is silently dropped."""
    return {
        "timestamp": datetime.utcnow(),
        "level":     "UNKNOWN",
        "service":   "unparsed",
        "message":   raw[:2000],
        "raw":       raw,
    }


def _norm_level(level: str) -> str:
    level = level.upper()
    return _LEVEL_NORMALISE.get(level, level if level in VALID_LEVELS else "UNKNOWN")


def _parse_ts(ts_str: str) -> datetime:
    if not ts_str:
        return datetime.utcnow()
    ts_str = ts_str[:26]   # trim microseconds beyond 6 digits
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return datetime.utcnow()
