import random

SERVICES = [
    "auth-service",
    "payment-service",
    "order-service",
    "inventory-service",
    "notification-service",
    "api-gateway",
    "user-service",
    "search-service",
]

ERROR_MESSAGES = [
    "Connection timeout after 30000ms to database replica-2",
    "NullPointerException in PaymentProcessor.process() at line 142",
    "Failed to acquire lock on resource: orders_table after 3 retries",
    "Circuit breaker OPEN for downstream service: inventory-service",
    "SSL handshake failed: certificate expired for domain payments.internal",
    "Kafka producer send failed: broker not available at localhost:9092",
    "HTTP 503 from upstream: payment-gateway after 2 retries",
    "Database connection pool exhausted: 50/50 connections in use",
    "Redis WRONGTYPE: key session:{id} holds wrong type",
    "gRPC deadline exceeded calling inventory-service.CheckStock",
]

WARN_MESSAGES = [
    "Response time degraded: {ms}ms (SLO threshold: 1000ms)",
    "Connection pool utilization at {pct}% — consider scaling",
    "Retry attempt {retry}/3 for request_id: req-{id}",
    "Cache miss rate elevated: {pct}% (baseline: <15%)",
    "Kafka consumer lag growing: {lag} messages behind on partition 0",
    "JWT token expiring in 5 minutes for user_id: usr-{id}",
    "Slow query detected: {ms}ms — SELECT * FROM orders WHERE user_id = {id}",
    "Disk usage at {pct}% on /var/log — rotation recommended",
    "Rate limit approaching for API key: key-{id} ({pct}% of quota used)",
]

INFO_MESSAGES = [
    "Request completed in {ms}ms — GET /api/v1/orders/{id}",
    "User usr-{id} authenticated successfully via OAuth2",
    "Order ord-{id} created and queued for processing",
    "Cache warmed: {count} entries loaded in {ms}ms",
    "Health check passed — all 5 upstream dependencies healthy",
    "Scheduled job cleanup_expired_sessions completed: {count} sessions removed",
    "Batch processed: {count} records in {ms}ms",
    "Kafka consumer connected: topic=rtla-logs, partition=0, offset={id}",
    "Config reload triggered — 3 values updated",
    "Payment txn-{id} settled successfully for ${amount}",
]

DEBUG_MESSAGES = [
    "Entering method: validatePaymentToken() for user usr-{id}",
    "Cache lookup: key=session:{id} — HIT (TTL: 843s remaining)",
    "SQL executed in {ms}ms: SELECT id, email FROM users WHERE id={id}",
    "gRPC call inventory-service.CheckStock returned in {ms}ms",
    "Middleware chain: [AuthMiddleware, RateLimitMiddleware, LoggingMiddleware]",
    "Deserialized request body: {count} fields validated",
]

LEVEL_WEIGHTS = {
    "INFO":  0.55,
    "WARN":  0.25,
    "ERROR": 0.12,
    "DEBUG": 0.08,
}


def _fill(template: str) -> str:
    return template.format(
        id=random.randint(1000, 9999),
        ms=random.randint(12, 4200),
        pct=random.randint(60, 99),
        retry=random.randint(1, 3),
        lag=random.randint(100, 5000),
        count=random.randint(10, 10000),
        amount=round(random.uniform(5.0, 999.99), 2),
    )


def generate_log_line(level: str = None) -> str:
    from datetime import datetime

    if level is None:
        level = random.choices(
            list(LEVEL_WEIGHTS.keys()),
            weights=list(LEVEL_WEIGHTS.values()),
        )[0]

    service = random.choice(SERVICES)
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    pool = {
        "ERROR": ERROR_MESSAGES,
        "WARN":  WARN_MESSAGES,
        "INFO":  INFO_MESSAGES,
        "DEBUG": DEBUG_MESSAGES,
    }
    message = _fill(random.choice(pool[level]))
    return f"{ts} {level} {service}: {message}"
