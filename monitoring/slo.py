"""
monitoring/slo.py
─────────────────
Provides two ways to instrument a stage:

1. @measure_stage("parse")          – decorator for sync functions
2. async with measure_stage_async("embed"):  – async context manager

Both:
  • Record duration in rtla_stage_latency_seconds{stage=...}
  • Increment rtla_slo_violations_total{stage=...} when budget exceeded
  • Log a WARNING when a violation occurs
"""

import asyncio
import functools
import logging
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Callable

from monitoring.metrics import SLO_BUDGETS_S, stage_latency, slo_violations_total

log = logging.getLogger("rtla.slo")


# ── sync context manager ───────────────────────────────────────────────────
@contextmanager
def measure_stage(stage: str):
    """
    Usage:
        with measure_stage("parse"):
            result = parser.parse(raw)
    """
    budget = SLO_BUDGETS_S.get(stage, float("inf"))
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        stage_latency.labels(stage=stage).observe(elapsed)
        if elapsed > budget:
            slo_violations_total.labels(stage=stage).inc()
            log.warning(
                "SLO VIOLATION stage=%s elapsed=%.3fms budget=%.3fms",
                stage,
                elapsed * 1000,
                budget * 1000,
            )


# ── async context manager ──────────────────────────────────────────────────
@asynccontextmanager
async def measure_stage_async(stage: str):
    """
    Usage:
        async with measure_stage_async("embed"):
            vec = await embedder.embed(text)
    """
    budget = SLO_BUDGETS_S.get(stage, float("inf"))
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        stage_latency.labels(stage=stage).observe(elapsed)
        if elapsed > budget:
            slo_violations_total.labels(stage=stage).inc()
            log.warning(
                "SLO VIOLATION stage=%s elapsed=%.3fms budget=%.3fms",
                stage,
                elapsed * 1000,
                budget * 1000,
            )


# ── sync decorator ─────────────────────────────────────────────────────────
def timed_stage(stage: str):
    """
    Usage:
        @timed_stage("parse")
        def parse_log(raw: str) -> dict: ...
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with measure_stage(stage):
                return fn(*args, **kwargs)
        return wrapper
    return decorator


# ── async decorator ────────────────────────────────────────────────────────
def async_timed_stage(stage: str):
    """
    Usage:
        @async_timed_stage("llm")
        async def call_llm(prompt: str) -> str: ...
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with measure_stage_async(stage):
                return await fn(*args, **kwargs)
        return wrapper
    return decorator