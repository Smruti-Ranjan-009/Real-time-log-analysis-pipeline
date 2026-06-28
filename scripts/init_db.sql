-- RTLA Phase 1: Log entries table
CREATE TABLE IF NOT EXISTS log_entries (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    level           VARCHAR(10)  NOT NULL,
    service         VARCHAR(100) NOT NULL,
    message         TEXT NOT NULL,
    raw             TEXT NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    parse_latency_ms FLOAT DEFAULT 0.0
);

-- Indexes for fast queries on level, time, and service
CREATE INDEX IF NOT EXISTS idx_log_level     ON log_entries(level);
CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log_entries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_log_service   ON log_entries(service);

-- Pipeline stats view (used by /stats endpoint)
CREATE OR REPLACE VIEW pipeline_stats AS
SELECT
    COUNT(*)                                          AS total_1h,
    COUNT(*) FILTER (WHERE level = 'ERROR')           AS errors_1h,
    COUNT(*) FILTER (WHERE level = 'WARN')            AS warnings_1h,
    COUNT(*) FILTER (WHERE level = 'INFO')            AS info_1h,
    COUNT(*) FILTER (WHERE level = 'DEBUG')           AS debug_1h,
    ROUND(AVG(parse_latency_ms)::numeric, 3)          AS avg_parse_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP
          (ORDER BY parse_latency_ms)::numeric, 3)    AS p95_parse_ms,
    MAX(timestamp)                                    AS last_seen
FROM log_entries
WHERE ingested_at > NOW() - INTERVAL '1 hour';
