---
title: RTLA Backend
emoji: ⚡
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# RTLA — Real-Time Log Intelligence Backend

FastAPI backend for the RTLA demo.
Exposes `/logs`, `/stats`, `/query`, `/index` endpoints.

Demo mode: uses SQLite + in-memory log generator (no Kafka required).
