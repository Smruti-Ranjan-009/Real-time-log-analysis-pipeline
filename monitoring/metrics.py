"""
monitoring/metrics.py
─────────────────────
Single source of truth for all RTLA Prometheus metrics.
Import `METRICS` anywhere in the codebase; never create new registries.

Latency budgets (milliseconds):
  ingest   50 ms  – log_generator → Kafka broker ACK
  kafka    30 ms  – Kafka broker → consumer poll
  parse    80 ms  – regex extract + classify
  embed    60 ms  – sentence-transformer encode
  llm     250 ms  – Groq Llama-3.3-70B round-trip
  delivery 20 ms  – DB insert / vector upsert
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    REGISTRY,
)

# ── SLO budgets in seconds (used by decorators & recording rules) ──────────
SLO_BUDGETS_S: dict[str, float] = {
    "ingest":   0.050,
    "kafka":    0.030,
    "parse":    0.080,
    "embed":    0.060,
    "llm":      0.250,
    "delivery": 0.020,
}

# Shared bucket boundaries that span sub-ms to multi-second for every stage
_LATENCY_BUCKETS = (
    0.001, 0.005, 0.010, 0.020, 0.030,
    0.050, 0.075, 0.100, 0.150, 0.200,
    0.250, 0.350, 0.500, 0.750, 1.0, 2.5,
)

# ── Per-stage latency histograms ───────────────────────────────────────────
stage_latency = Histogram(
    "rtla_stage_latency_seconds",
    "End-to-end latency per pipeline stage",
    labelnames=["stage"],          # ingest | kafka | parse | embed | llm | delivery
    buckets=_LATENCY_BUCKETS,
)

# ── SLO violation counters ─────────────────────────────────────────────────
slo_violations_total = Counter(
    "rtla_slo_violations_total",
    "Number of times a stage exceeded its latency budget",
    labelnames=["stage"],
)

# ── Throughput / error counters ────────────────────────────────────────────
logs_ingested_total = Counter(
    "rtla_logs_ingested_total",
    "Total log messages received by the Kafka consumer",
    labelnames=["level"],          # DEBUG | INFO | WARN | ERROR | CRITICAL
)

logs_parsed_total = Counter(
    "rtla_logs_parsed_total",
    "Total log messages successfully parsed",
)

parse_errors_total = Counter(
    "rtla_parse_errors_total",
    "Log messages that failed parsing",
)

embed_errors_total = Counter(
    "rtla_embed_errors_total",
    "Embedding calls that raised an exception",
)

llm_calls_total = Counter(
    "rtla_llm_calls_total",
    "Total LLM inference calls",
    labelnames=["tier"],           # primary | fallback | cache
)

llm_errors_total = Counter(
    "rtla_llm_errors_total",
    "LLM calls that raised an exception or returned an error",
    labelnames=["tier"],
)

rag_queries_total = Counter(
    "rtla_rag_queries_total",
    "Total RAG queries (vector search + LLM)",
)

# ── Gauge: in-flight / queue depth ────────────────────────────────────────
kafka_consumer_lag = Gauge(
    "rtla_kafka_consumer_lag_messages",
    "Estimated Kafka consumer lag (messages behind)",
)

active_rag_requests = Gauge(
    "rtla_active_rag_requests",
    "Number of RAG requests currently in-flight",
)

# ── Build info (for dashboard filters) ────────────────────────────────────
build_info = Gauge(
    "rtla_build_info",
    "Static build metadata",
    labelnames=["version", "phase"],
)
build_info.labels(version="0.3.0", phase="3").set(1)