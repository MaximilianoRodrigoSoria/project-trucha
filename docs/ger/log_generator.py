"""
log_generator.py
=================
Genera logs sintéticos con causalidad (trace_id / span_id / caused_by) para
simular el comportamiento real de un sistema con dos endpoints:

  - GET  /api/users/{id}      -> flujo de lectura (gateway -> auth -> cache -> db)
  - POST /api/payments        -> flujo de pago (gateway -> auth -> fraude -> saldo
                                  -> gateway de pago -> ledger -> cola -> notificación)

Además emite eventos de infraestructura sueltos (health checks, memoria, etc.)
que NO pertenecen a una traza de request, para tener variedad.

Salida: un archivo JSONL (1 log por línea) en /mnt/user-data/outputs/logs.jsonl
Cada línea es un dict JSON con:
  timestamp, event_id, trace_id, span_id, caused_by, service,
  log_type, level, endpoint, message, metadata

El campo `caused_by` apunta al event_id del log que lo originó, así se puede
reconstruir la cadena causal completa de una traza (útil para el grafo).

50 log_type distintos en total (ver LOG_CATALOG).
"""

import json
import random
import uuid
import argparse
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 1. CATÁLOGO DE 50 TIPOS DE LOG
#    key -> (service, level, template_de_mensaje)
# ---------------------------------------------------------------------------
LOG_CATALOG = {
    # ---- HTTP / Gateway (compartidos por ambos endpoints) ----
    "http_request_received":      ("api-gateway",     "INFO",  "Request recibido: {method} {endpoint} desde IP {ip}"),
    "rate_limit_check_passed":    ("api-gateway",     "INFO",  "Rate limit OK para IP {ip} ({rate_count}/{rate_limit})"),
    "rate_limit_exceeded":        ("api-gateway",     "WARN",  "Rate limit excedido para IP {ip}, request rechazado (429)"),
    "http_response_sent":         ("api-gateway",     "INFO",  "Response enviado {status_code} para {endpoint} en {latency_ms}ms"),
    "request_completed":          ("api-gateway",     "INFO",  "Request completado, duración total {latency_ms}ms"),
    "unhandled_exception":        ("api-gateway",     "CRITICAL", "Excepción no controlada procesando {endpoint}: {error_detail}"),

    # ---- Auth ----
    "auth_token_validated":       ("auth-service",    "INFO",  "Token JWT validado correctamente para user {user_id}"),
    "auth_token_invalid":         ("auth-service",    "WARN",  "Token JWT inválido o malformado (401)"),
    "auth_token_expired":         ("auth-service",    "WARN",  "Token JWT expirado para user {user_id} (401)"),
    "authorization_granted":      ("auth-service",    "INFO",  "Permisos verificados: user {user_id} autorizado para {endpoint}"),
    "authorization_denied":       ("auth-service",    "WARN",  "user {user_id} no tiene permisos para {endpoint} (403)"),

    # ---- Cache ----
    "cache_lookup_hit":           ("cache-service",   "INFO",  "Cache HIT para key user:{user_id}"),
    "cache_lookup_miss":          ("cache-service",   "INFO",  "Cache MISS para key user:{user_id}, se consulta DB"),
    "cache_write_success":        ("cache-service",   "INFO",  "Cache actualizado para key user:{user_id} (TTL {ttl}s)"),
    "cache_write_failed":         ("cache-service",   "WARN",  "Fallo al escribir cache para key user:{user_id}: {error_detail}"),

    # ---- Database ----
    "db_connection_acquired":     ("db-service",      "INFO",  "Conexión a DB adquirida del pool (in_use={pool_used}/{pool_size})"),
    "db_connection_pool_exhausted": ("db-service",    "ERROR", "Pool de conexiones agotado ({pool_used}/{pool_size})"),
    "db_query_executed":          ("db-service",      "INFO",  "Query ejecutada: {query} ({latency_ms}ms)"),
    "db_query_timeout":           ("db-service",      "ERROR", "Timeout ejecutando query tras {latency_ms}ms"),
    "db_query_result_found":      ("db-service",      "INFO",  "Registro encontrado para user {user_id}"),
    "db_record_not_found":        ("db-service",      "WARN",  "user {user_id} no existe en DB (404)"),
    "response_serialized":        ("api-gateway",     "INFO",  "Response serializado para {endpoint} (user {user_id})"),

    # ---- Validación / Payments request ----
    "request_body_validated":     ("payments-service","INFO",  "Body de payment request validado OK"),
    "request_validation_failed":  ("payments-service","WARN",  "Body inválido: {error_detail} (400)"),
    "idempotency_key_checked":    ("payments-service","INFO",  "Idempotency key {idem_key} verificada, no existe duplicado"),
    "idempotency_key_duplicate":  ("payments-service","INFO",  "Idempotency key {idem_key} ya procesada, se devuelve resultado cacheado (200)"),

    # ---- Fraude / Saldo ----
    "fraud_check_passed":         ("fraud-service",   "INFO",  "Chequeo antifraude OK para transacción {payment_id} (score {fraud_score})"),
    "fraud_check_flagged":        ("fraud-service",   "WARN",  "Transacción {payment_id} marcada como sospechosa (score {fraud_score}), bloqueada (403)"),
    "account_balance_verified":   ("ledger-service",  "INFO",  "Saldo verificado para cuenta {account_id}: disponible ${balance}"),
    "insufficient_funds":         ("ledger-service",  "WARN",  "Saldo insuficiente en cuenta {account_id} para monto ${amount} (402)"),

    # ---- Payment Gateway externo ----
    "payment_gateway_request_sent":     ("payment-gateway", "INFO",  "Solicitud enviada a pasarela externa por ${amount} {currency}, payment_id {payment_id}"),
    "payment_gateway_response_received":("payment-gateway", "INFO",  "Respuesta de pasarela recibida en {latency_ms}ms: {gateway_status}"),
    "payment_gateway_timeout":          ("payment-gateway", "ERROR", "Timeout esperando respuesta de pasarela tras {latency_ms}ms"),
    "payment_gateway_error":            ("payment-gateway", "ERROR", "Pasarela externa devolvió error: {error_detail}"),
    "payment_authorized":               ("payment-gateway", "INFO",  "Pago {payment_id} autorizado por ${amount} {currency}"),
    "payment_declined":                 ("payment-gateway", "WARN",  "Pago {payment_id} rechazado por la pasarela: {error_detail}"),

    # ---- Ledger / Mensajería / Notificaciones ----
    "ledger_entry_created":       ("ledger-service",  "INFO",  "Asiento contable creado para payment {payment_id}, cuenta {account_id}"),
    "notification_queued":        ("payments-service","INFO",  "Notificación de pago {payment_id} encolada para envío"),
    "message_published_to_queue": ("message-broker",  "INFO",  "Mensaje publicado en cola 'payment-notifications' (payment {payment_id})"),
    "message_consumed_by_worker": ("notification-worker","INFO","Worker consumió mensaje de payment {payment_id} de la cola"),
    "receipt_generated":          ("notification-worker","INFO","Comprobante generado y enviado a user {user_id} para payment {payment_id}"),

    # ---- Resiliencia ----
    "retry_attempted":            ("infra",           "WARN",  "Reintento #{retry_count} para operación {op_name}"),
    "circuit_breaker_opened":     ("infra",           "ERROR", "Circuit breaker ABIERTO para {op_name} tras {fail_count} fallos consecutivos"),
    "circuit_breaker_closed":     ("infra",           "INFO",  "Circuit breaker CERRADO para {op_name}, servicio recuperado"),
    "dead_letter_queue_message":  ("message-broker",  "ERROR", "Mensaje enviado a dead-letter-queue tras {retry_count} reintentos fallidos"),

    # ---- Infraestructura / background (sin trace_id de request) ----
    "health_check_ok":            ("infra",           "INFO",  "Health check OK para servicio {service_name}"),
    "health_check_failed":        ("infra",           "ERROR", "Health check FALLIDO para servicio {service_name}"),
    "service_started":            ("infra",           "INFO",  "Servicio {service_name} iniciado, versión {version}"),
    "disk_space_warning":         ("infra",           "WARN",  "Espacio en disco bajo en {service_name}: {disk_pct}% usado"),
    "memory_usage_high":          ("infra",           "WARN",  "Uso de memoria alto en {service_name}: {mem_pct}%"),
}

assert len(LOG_CATALOG) == 50, f"Se esperaban 50 tipos de log, hay {len(LOG_CATALOG)}"


# ---------------------------------------------------------------------------
# 2. HELPERS
# ---------------------------------------------------------------------------
def new_id():
    return uuid.uuid4().hex[:12]


def make_log(catalog_key, ctx, trace_id, caused_by, ts):
    """Arma un log entry a partir del catálogo + contexto de valores random."""
    service, level, template = LOG_CATALOG[catalog_key]
    event_id = new_id()
    message = template.format(**ctx)
    return {
        "timestamp": ts.isoformat(timespec="milliseconds"),
        "event_id": event_id,
        "trace_id": trace_id,
        "span_id": new_id(),
        "caused_by": caused_by,
        "service": service,
        "log_type": catalog_key,
        "level": level,
        "endpoint": ctx.get("endpoint"),
        "message": message,
        "metadata": {k: v for k, v in ctx.items() if k not in ("endpoint",)},
    }


def rand_ip():
    return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"


def advance(ts, lo=15, hi=400):
    return ts + timedelta(milliseconds=random.randint(lo, hi))


# ---------------------------------------------------------------------------
# 3. FLUJO A: GET /api/users/{id}
#    Simula la cadena causal completa, con puntos de fallo aleatorios.
# ---------------------------------------------------------------------------
def generate_get_user_trace(start_ts):
    logs = []
    trace_id = new_id()
    ts = start_ts
    caused_by = None
    user_id = random.randint(1000, 9999)
    ctx = {
        "endpoint": "GET /api/users/{id}",
        "method": "GET",
        "ip": rand_ip(),
        "user_id": user_id,
    }

    def emit(key, **extra):
        nonlocal ts, caused_by
        c = {**ctx, **extra}
        entry = make_log(key, c, trace_id, caused_by, ts)
        logs.append(entry)
        caused_by = entry["event_id"]
        ts = advance(ts)
        return entry

    emit("http_request_received")

    # Rate limit
    if random.random() < 0.05:
        emit("rate_limit_exceeded", rate_count=105, rate_limit=100)
        emit("http_response_sent", status_code=429, latency_ms=random.randint(5, 20))
        return logs
    emit("rate_limit_check_passed", rate_count=random.randint(1, 90), rate_limit=100)

    # Auth
    auth_roll = random.random()
    if auth_roll < 0.04:
        emit("auth_token_invalid")
        emit("http_response_sent", status_code=401, latency_ms=random.randint(10, 40))
        return logs
    elif auth_roll < 0.08:
        emit("auth_token_expired")
        emit("http_response_sent", status_code=401, latency_ms=random.randint(10, 40))
        return logs
    emit("auth_token_validated")

    # Authorization
    if random.random() < 0.03:
        emit("authorization_denied")
        emit("http_response_sent", status_code=403, latency_ms=random.randint(10, 40))
        return logs
    emit("authorization_granted")

    # Cache
    if random.random() < 0.55:
        emit("cache_lookup_hit")
    else:
        emit("cache_lookup_miss")

        # DB path
        if random.random() < 0.03:
            emit("db_connection_pool_exhausted", pool_used=50, pool_size=50)
            emit("retry_attempted", retry_count=1, op_name="db_connection")
            if random.random() < 0.5:
                emit("circuit_breaker_opened", op_name="db-service", fail_count=5)
                emit("unhandled_exception", error_detail="db pool exhausted, circuit open")
                emit("http_response_sent", status_code=503, latency_ms=random.randint(200, 800))
                return logs
        emit("db_connection_acquired", pool_used=random.randint(1, 30), pool_size=50)

        if random.random() < 0.04:
            emit("db_query_timeout", latency_ms=random.randint(3000, 5000))
            emit("retry_attempted", retry_count=1, op_name="db_query")
            emit("unhandled_exception", error_detail="db query timeout on retry")
            emit("http_response_sent", status_code=500, latency_ms=random.randint(3000, 5500))
            return logs
        emit("db_query_executed", query=f"SELECT * FROM users WHERE id={user_id}", latency_ms=random.randint(5, 120))

        if random.random() < 0.06:
            emit("db_record_not_found")
            emit("http_response_sent", status_code=404, latency_ms=random.randint(20, 80))
            return logs
        emit("db_query_result_found")

        if random.random() < 0.1:
            emit("cache_write_failed", error_detail="connection reset")
        else:
            emit("cache_write_success", ttl=300)

    emit("response_serialized")
    emit("http_response_sent", status_code=200, latency_ms=random.randint(15, 150))
    emit("request_completed", latency_ms=(ts - start_ts) // timedelta(milliseconds=1))
    return logs


# ---------------------------------------------------------------------------
# 4. FLUJO B: POST /api/payments
# ---------------------------------------------------------------------------
def generate_payment_trace(start_ts):
    logs = []
    trace_id = new_id()
    ts = start_ts
    caused_by = None
    user_id = random.randint(1000, 9999)
    account_id = f"acc_{random.randint(100000,999999)}"
    payment_id = f"pay_{new_id()}"
    amount = round(random.uniform(5, 2500), 2)
    ctx = {
        "endpoint": "POST /api/payments",
        "method": "POST",
        "ip": rand_ip(),
        "user_id": user_id,
        "account_id": account_id,
        "payment_id": payment_id,
        "amount": amount,
        "currency": "USD",
        "idem_key": new_id(),
    }

    def emit(key, **extra):
        nonlocal ts, caused_by
        c = {**ctx, **extra}
        entry = make_log(key, c, trace_id, caused_by, ts)
        logs.append(entry)
        caused_by = entry["event_id"]
        ts = advance(ts)
        return entry

    emit("http_request_received")

    if random.random() < 0.03:
        emit("request_validation_failed", error_detail="campo 'amount' faltante")
        emit("http_response_sent", status_code=400, latency_ms=random.randint(5, 30))
        return logs
    emit("request_body_validated")

    if random.random() < 0.03:
        emit("auth_token_invalid")
        emit("http_response_sent", status_code=401, latency_ms=random.randint(10, 40))
        return logs
    emit("auth_token_validated")

    if random.random() < 0.02:
        emit("idempotency_key_duplicate")
        emit("http_response_sent", status_code=200, latency_ms=random.randint(5, 20))
        return logs
    emit("idempotency_key_checked")

    fraud_score = round(random.uniform(0, 1), 2)
    if fraud_score > 0.9:
        emit("fraud_check_flagged", fraud_score=fraud_score)
        emit("http_response_sent", status_code=403, latency_ms=random.randint(30, 100))
        return logs
    emit("fraud_check_passed", fraud_score=fraud_score)

    balance = round(random.uniform(0, 5000), 2)
    emit("account_balance_verified", balance=balance)
    if balance < amount:
        emit("insufficient_funds")
        emit("http_response_sent", status_code=402, latency_ms=random.randint(20, 80))
        return logs

    emit("payment_gateway_request_sent")
    gw_roll = random.random()
    if gw_roll < 0.04:
        emit("payment_gateway_timeout", latency_ms=random.randint(4000, 8000))
        emit("retry_attempted", retry_count=1, op_name="payment_gateway_call")
        if random.random() < 0.4:
            emit("circuit_breaker_opened", op_name="payment-gateway", fail_count=5)
            emit("http_response_sent", status_code=503, latency_ms=random.randint(4000, 9000))
            return logs
    elif gw_roll < 0.08:
        emit("payment_gateway_error", error_detail="issuer_unavailable")
        emit("payment_declined", error_detail="issuer_unavailable")
        emit("http_response_sent", status_code=502, latency_ms=random.randint(200, 900))
        return logs

    emit("payment_gateway_response_received", latency_ms=random.randint(150, 900), gateway_status="approved")

    if random.random() < 0.05:
        emit("payment_declined", error_detail="card_declined_by_issuer")
        emit("http_response_sent", status_code=402, latency_ms=random.randint(200, 900))
        return logs

    emit("payment_authorized")
    emit("ledger_entry_created")
    emit("notification_queued")
    emit("message_published_to_queue")

    if random.random() < 0.03:
        emit("retry_attempted", retry_count=1, op_name="notification_consume")
        emit("dead_letter_queue_message", retry_count=3)
    else:
        emit("message_consumed_by_worker")
        emit("receipt_generated")

    emit("http_response_sent", status_code=200, latency_ms=random.randint(200, 1200))
    emit("request_completed", latency_ms=(ts - start_ts) // timedelta(milliseconds=1))
    return logs


# ---------------------------------------------------------------------------
# 5. Eventos de infraestructura sueltos (sin trace_id de negocio)
# ---------------------------------------------------------------------------
INFRA_SERVICES = ["api-gateway", "auth-service", "cache-service", "db-service",
                   "payment-gateway", "ledger-service", "notification-worker", "message-broker"]

def generate_infra_event(start_ts):
    key = random.choice([
        "health_check_ok", "health_check_ok", "health_check_ok",  # más frecuente
        "health_check_failed", "service_started",
        "disk_space_warning", "memory_usage_high", "circuit_breaker_closed",
    ])
    ctx = {
        "endpoint": None,
        "service_name": random.choice(INFRA_SERVICES),
        "version": f"1.{random.randint(0,9)}.{random.randint(0,20)}",
        "disk_pct": random.randint(70, 97),
        "mem_pct": random.randint(75, 98),
        "op_name": random.choice(["db_connection", "payment_gateway_call", "cache_write"]),
    }
    trace_id = new_id()  # cada evento de infra es su propia "traza" mínima
    return [make_log(key, ctx, trace_id, None, start_ts)]


# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generador de logs sintéticos con causalidad")
    parser.add_argument("--get-traces", type=int, default=150, help="Cantidad de trazas GET /users")
    parser.add_argument("--payment-traces", type=int, default=150, help="Cantidad de trazas POST /payments")
    parser.add_argument("--infra-events", type=int, default=100, help="Cantidad de eventos de infra sueltos")
    parser.add_argument("--output", type=str, default="/mnt/user-data/outputs/logs.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    all_logs = []
    base_ts = datetime.now(timezone.utc) - timedelta(hours=6)

    for _ in range(args.get_traces):
        t = base_ts + timedelta(milliseconds=random.randint(0, 6 * 3600 * 1000))
        all_logs.extend(generate_get_user_trace(t))

    for _ in range(args.payment_traces):
        t = base_ts + timedelta(milliseconds=random.randint(0, 6 * 3600 * 1000))
        all_logs.extend(generate_payment_trace(t))

    for _ in range(args.infra_events):
        t = base_ts + timedelta(milliseconds=random.randint(0, 6 * 3600 * 1000))
        all_logs.extend(generate_infra_event(t))

    all_logs.sort(key=lambda x: x["timestamp"])

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in all_logs:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    types_used = len(set(l["log_type"] for l in all_logs))
    print(f"Generados {len(all_logs)} logs en {args.output}")
    print(f"Tipos de log distintos usados: {types_used}/50")
    print(f"Trazas GET: {args.get_traces} | Trazas payment: {args.payment_traces} | Infra: {args.infra_events}")


if __name__ == "__main__":
    main()
