"""
RTLA Phase 1 — Kafka Consumer
Runs in a background daemon thread.
Consumes from the rtla-logs topic, parses each message, stores to PostgreSQL.
Phase 3 will instrument this with Prometheus counters + histograms.
"""

import logging
import os
import threading
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable, KafkaError
from dotenv import load_dotenv

from .parser import parse_log
from .database import insert_log

load_dotenv()
logger = logging.getLogger("rtla.kafka_consumer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC     = os.getenv("KAFKA_TOPIC", "rtla-logs")
KAFKA_GROUP     = os.getenv("KAFKA_GROUP_ID", "rtla-consumer-group")

_stop_event:        threading.Event         = threading.Event()
_consumer_thread:   Optional[threading.Thread] = None

# Simple in-memory counters — Phase 3 will promote these to Prometheus
_counters = {
    "received":   0,
    "parsed_ok":  0,
    "parse_fail": 0,
    "db_error":   0,
}


def get_counters() -> dict:
    return dict(_counters)


# ── Internal loop ─────────────────────────────────────────────────────────────

def _consume_loop() -> None:
    logger.info(
        f"Kafka consumer starting — broker={KAFKA_BOOTSTRAP} "
        f"topic={KAFKA_TOPIC} group={KAFKA_GROUP}"
    )

    consumer = _create_consumer()
    if consumer is None:
        logger.error("Could not create Kafka consumer. Consumer thread exiting.")
        return

    try:
        while not _stop_event.is_set():
            records = consumer.poll(timeout_ms=1000)
            for tp, messages in records.items():
                for msg in messages:
                    if _stop_event.is_set():
                        break

                    _counters["received"] += 1
                    raw = msg.value

                    entry = parse_log(raw)
                    if entry is None:
                        _counters["parse_fail"] += 1
                        continue

                    _counters["parsed_ok"] += 1

                    try:
                        row_id = insert_log(entry)
                        logger.debug(
                            f"[{entry['level']}] {entry['service']} → row {row_id} "
                            f"(parse: {entry['parse_latency_ms']:.2f} ms)"
                        )
                    except Exception as db_err:
                        _counters["db_error"] += 1
                        logger.error(f"DB insert failed: {db_err}")

    except KafkaError as ke:
        logger.error(f"Kafka error in consumer loop: {ke}")
    except Exception as e:
        logger.exception(f"Unexpected error in consumer loop: {e}")
    finally:
        consumer.close()
        logger.info(
            f"Kafka consumer stopped. Stats: "
            f"received={_counters['received']} "
            f"parsed_ok={_counters['parsed_ok']} "
            f"db_errors={_counters['db_error']}"
        )


def _create_consumer(retries: int = 10) -> Optional[KafkaConsumer]:
    for attempt in range(1, retries + 1):
        try:
            return KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=KAFKA_GROUP,
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda m: m.decode("utf-8", errors="replace"),
                consumer_timeout_ms=1000,   # allows checking _stop_event
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
            )
        except NoBrokersAvailable:
            import time
            logger.warning(f"Kafka not reachable — attempt {attempt}/{retries}. Retrying in 3s…")
            time.sleep(3)
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def start_consumer() -> None:
    global _consumer_thread
    _stop_event.clear()
    _consumer_thread = threading.Thread(
        target=_consume_loop,
        name="kafka-consumer",
        daemon=True,
    )
    _consumer_thread.start()
    logger.info("Kafka consumer thread started.")


def stop_consumer() -> None:
    logger.info("Requesting Kafka consumer shutdown…")
    _stop_event.set()
    if _consumer_thread and _consumer_thread.is_alive():
        _consumer_thread.join(timeout=8)
    logger.info("Kafka consumer thread stopped.")
