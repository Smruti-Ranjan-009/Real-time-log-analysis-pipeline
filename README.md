# RTLA — Real-Time Log Intelligence System

A production-grade log analysis pipeline with explicit latency SLOs and graceful degradation.

## Phase 1: Log Ingestion + Parsing Pipeline

**Stack:** Kafka · FastAPI · PostgreSQL · Python 3.11

---

## Setup

### 1. Create conda environment

```bash
conda create -n rtla python=3.11 -y
conda activate rtla
pip install -r requirements.txt
```

### 2. Start infrastructure

```bash
docker-compose up -d
```

Wait ~20 seconds for Kafka and PostgreSQL to be healthy:

```bash
docker-compose ps    # all should show "healthy"
```

### 3. Start the FastAPI consumer

```bash
# From the rtla/ directory
uvicorn consumer.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Start the log generator (new terminal)

```bash
conda activate rtla
# From the rtla/ directory
python log_generator/generator.py
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /logs?limit=50` | Recent logs (all levels) |
| `GET /logs?level=ERROR` | Filter by level |
| `GET /logs/errors` | Recent errors only |
| `GET /stats` | Pipeline stats (last 1 hour) |
| `GET /consumer/stats` | In-memory consumer counters |
| `GET /docs` | Swagger UI |

---

## Latency Budget (Phase 1)

| Stage | Budget | Measured via |
|---|---|---|
| Log generation → Kafka | 50 ms | generator linger_ms |
| Kafka → consumer | 30 ms | consumer poll interval |
| Parse + classify | 80 ms | `parse_latency_ms` column |
| DB insert | 40 ms | psycopg2 round-trip |
| **Total target** | **< 500 ms** | Phase 3 Prometheus p95 |

---

## Folder Structure

```
rtla/
├── docker-compose.yml
├── .env
├── requirements.txt
├── README.md
├── log_generator/
│   ├── generator.py       # Kafka producer (run directly)
│   └── templates.py       # Synthetic log message templates
├── consumer/
│   ├── __init__.py
│   ├── main.py            # FastAPI app
│   ├── kafka_consumer.py  # Background consumer thread
│   ├── parser.py          # Log parsing + timestamp normalization
│   └── database.py        # PostgreSQL queries
└── scripts/
    └── init_db.sql        # Schema (also run by Docker entrypoint)
```

---

## Stopping

```bash
# Stop generator: Ctrl+C in its terminal
# Stop FastAPI: Ctrl+C in its terminal
docker-compose down        # stop containers (keeps volume)
docker-compose down -v     # stop + wipe postgres data
```
