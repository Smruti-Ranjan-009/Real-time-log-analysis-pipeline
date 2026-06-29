"""monitoring – Prometheus metrics + SLO instrumentation for RTLA Phase 3."""
from monitoring.metrics import (
    SLO_BUDGETS_S,
    stage_latency,
    slo_violations_total,
    logs_ingested_total,
    logs_parsed_total,
    parse_errors_total,
    embed_errors_total,
    llm_calls_total,
    llm_errors_total,
    rag_queries_total,
    kafka_consumer_lag,
    active_rag_requests,
)
from monitoring.slo import measure_stage, measure_stage_async, timed_stage, async_timed_stage

__all__ = [
    "SLO_BUDGETS_S",
    "stage_latency",
    "slo_violations_total",
    "logs_ingested_total",
    "logs_parsed_total",
    "parse_errors_total",
    "embed_errors_total",
    "llm_calls_total",
    "llm_errors_total",
    "rag_queries_total",
    "kafka_consumer_lag",
    "active_rag_requests",
    "measure_stage",
    "measure_stage_async",
    "timed_stage",
    "async_timed_stage",
]