"""
consumer/kafka_consumer.py  (Phase 3 — instrumented)
─────────────────────────────────────────────────────
Measures:
  • kafka stage   – time from message produce timestamp → consumer poll receipt
  • delivery stage – time to write parsed log to PostgreSQL
"""

import json
import logging
import threading
import time
from typing import Optional

from confluent_kafka import Consumer, KafkaError, KafkaException

from consumer.database import insert_log
from consumer.parser import parse_log
from monitoring import (
    logs_ingested_total,
    logs_parsed_total,
    parse_errors_total,
    kafka_consumer_lag,
    measure_stage,
)
from monitoring.metrics import stage_latency, slo_violations_total, SLO_BUDGETS_S

log = logging.getLogger("rtla.consumer")

TOPIC = "rtla-logs"
BOOTSTRAP = "localhost:9092"
GROUP_ID = "rtla-consumer-group"


def _record_kafka_latency(msg) -> None:
    """
    Estimate Kafka transit latency using the message timestamp.
    confluent_kafka returns the broker-assigned timestamp in milliseconds.
    """
    ts_type, ts_ms = msg.timestamp()
    if ts_type in (1, 2) and ts_ms > 0:   # 1=CREATE_TIME, 2=LOG_APPEND_TIME
        now_ms = time.time() * 1000
        elapsed_s = (now_ms - ts_ms) / 1000.0
        # Clamp to sane range (clock skew guard)
        elapsed_s = max(0.0, min(elapsed_s, 30.0))
        stage_latency.labels(stage="kafka").observe(elapsed_s)
        if elapsed_s > SLO_BUDGETS_S["kafka"]:
            slo_violations_total.labels(stage="kafka").inc()
            log.warning(
                "SLO VIOLATION stage=kafka elapsed=%.3fms budget=%.3fms",
                elapsed_s * 1000,
                SLO_BUDGETS_S["kafka"] * 1000,
            )


class RtlaKafkaConsumer:
    def __init__(self):
        self._consumer: Optional[Consumer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.stats: dict = {
            "consumed": 0,
            "parsed": 0,
            "errors": 0,
            "slo_violations": 0,
        }

    def start(self):
        self._consumer = Consumer(
            {
                "bootstrap.servers": BOOTSTRAP,
                "group.id": GROUP_ID,
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
                "statistics.interval.ms": 5000,   # enables lag reporting
            }
        )
        self._consumer.subscribe([TOPIC])
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("Kafka consumer started — topic=%s group=%s", TOPIC, GROUP_ID)

    def stop(self):
        self._running = False
        if self._consumer:
            self._consumer.close()

    def _poll_loop(self):
        while self._running:
            try:
                msg = self._consumer.poll(timeout=0.1)   # 100 ms poll timeout
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.error("Kafka error: %s", msg.error())
                    continue

                self._handle_message(msg)

            except KafkaException as exc:
                log.exception("KafkaException in poll loop: %s", exc)
            except Exception as exc:
                log.exception("Unexpected error in poll loop: %s", exc)

    def _handle_message(self, msg):
        # ── kafka transit latency ──────────────────────────────────────────
        _record_kafka_latency(msg)

        raw: str = msg.value().decode("utf-8", errors="replace")
        self.stats["consumed"] += 1

        # ── parse stage (instrumented in parser.py via @timed_stage) ──────
        try:
            parsed = parse_log(raw)
        except Exception as exc:
            log.warning("Parse failed: %s | raw=%s", exc, raw[:120])
            parse_errors_total.inc()
            self.stats["errors"] += 1
            return

        if parsed is None:
            parse_errors_total.inc()
            self.stats["errors"] += 1
            return

        # Increment log level counter
        level = parsed.get("level", "UNKNOWN").upper()
        logs_ingested_total.labels(level=level).inc()
        logs_parsed_total.inc()
        self.stats["parsed"] += 1

        # ── delivery stage ─────────────────────────────────────────────────
        with measure_stage("delivery"):
            try:
                insert_log(parsed)
            except Exception as exc:
                log.error("DB insert failed: %s", exc)
                self.stats["errors"] += 1

    def get_stats(self) -> dict:
        return dict(self.stats)