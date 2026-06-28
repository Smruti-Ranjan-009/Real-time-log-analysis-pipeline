"""
RTLA Phase 1 — Log Generator
Produces realistic synthetic logs to Kafka at a configurable rate.
Simulates periodic error bursts to test the pipeline.

Run from rtla/ directory:
    python log_generator/generator.py
"""

import time
import random
import logging
import os
import signal
import sys

# Add parent dir to path so we can import templates
sys.path.insert(0, os.path.dirname(__file__))
from templates import generate_log_line

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [generator] %(levelname)s: %(message)s",
)
logger = logging.getLogger("rtla.generator")

KAFKA_BOOTSTRAP    = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC        = os.getenv("KAFKA_TOPIC", "rtla-logs")
RATE_PER_SECOND    = float(os.getenv("LOG_RATE_PER_SECOND", "3.0"))
BURST_PROBABILITY  = 0.008   # ~0.8% chance per message → burst every ~40s at 3/s
BURST_SIZE_RANGE   = (8, 20)


def create_producer(retries: int = 10) -> KafkaProducer:
    """Retry until Kafka is ready (useful on first docker-compose up)."""
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: v.encode("utf-8"),
                acks="all",
                retries=3,
                linger_ms=5,          # small batching for throughput
            )
            logger.info(f"Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready — attempt {attempt}/{retries}. Retrying in 3s…")
            time.sleep(3)
    raise RuntimeError("Could not connect to Kafka after multiple retries.")


def main():
    producer = create_producer()
    count = 0
    burst_count = 0

    def shutdown(sig, frame):
        logger.info(f"Shutting down. Total logs sent: {count} | Bursts: {burst_count}")
        producer.flush(timeout=5)
        producer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(
        f"Generating logs at {RATE_PER_SECOND}/sec → topic '{KAFKA_TOPIC}'\n"
        f"  Burst probability: {BURST_PROBABILITY*100:.1f}% | Burst size: {BURST_SIZE_RANGE}\n"
        f"  Press Ctrl+C to stop."
    )

    sleep_interval = 1.0 / RATE_PER_SECOND

    while True:
        log_line = generate_log_line()
        producer.send(KAFKA_TOPIC, value=log_line)
        count += 1

        # Log progress every 30 messages
        if count % 30 == 0:
            logger.info(f"[{count} sent] Latest: {log_line[:80]}")

        # Simulate random error burst
        if random.random() < BURST_PROBABILITY:
            burst_size = random.randint(*BURST_SIZE_RANGE)
            burst_count += 1
            logger.warning(f"⚡ Injecting error burst #{burst_count}: {burst_size} ERRORs")
            for _ in range(burst_size):
                producer.send(KAFKA_TOPIC, value=generate_log_line(level="ERROR"))
                count += 1

        time.sleep(sleep_interval)


if __name__ == "__main__":
    main()
