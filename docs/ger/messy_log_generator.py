"""
messy_log_generator.py
======================
Contraparte "sucia" de log_generator.py.

Simula cómo son los logs en la mayoría de los sistemas reales: sin
estándar, mezclando formatos, con campos faltantes, timestamps
inconsistentes, niveles mal escritos, stack traces crudos pegados en
una sola línea gigante, texto en dos idiomas, etc.

Regla del sistema real simulado: TODA línea lleva al menos un traceId.
Aunque el nombre del campo y el formato cambian por línea, el trace_id
siempre está presente y es compartido por todas las líneas de la misma
transacción (igual que en los logs prolijos), así el agrupamiento por
traza funciona aunque haya que parsear formatos distintos.

Reutiliza los mismos escenarios de negocio que log_generator.py
(consulta de usuario / pago) para que después puedas comparar cómo se
ingesta lo mismo cuando está bien vs. mal estructurado.

Salida: texto plano línea por línea (NO es JSONL válido a propósito)
en /mnt/user-data/outputs/messy_logs.log
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

random.seed(7)

USERS = list(range(1000, 9999))
SERVICES = ["api-gw", "authsvc", "cache", "db-primary", "payments", "fraud-chk",
            "ledger", "notif-worker", "gw-payments", "GATEWAY"]
LEVELS_MESSY = ["INFO", "info", "Info", "WARN", "warning", "WARNING", "Warn",
                "ERROR", "error", "Err", "ERR", "CRITICAL", "crit", "DEBUG", "debug", "trace"]

TRACE_KEYS = ["reqId", "request_id", "trace", "rid", "corrId", "tid", "trace_id"]

STACK_TRACE = (
    "Traceback (most recent call last): File \"payments.py\", line 233, in charge "
    "raise GatewayTimeout('upstream did not respond') GatewayTimeout: upstream did not respond "
    "at com.app.PaymentService.charge(PaymentService.java:118) at com.app.Controller.handle(Controller.java:44)"
)


def rand_ts_variant():
    """Timestamps con formatos totalmente inconsistentes entre sí."""
    base = datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 6),
                                                    minutes=random.randint(0, 59),
                                                    seconds=random.randint(0, 59))
    fmt = random.choice([
        lambda d: d.strftime("%b %d %H:%M:%S"),                 # Aug 15 09:47:15  (sin año, sin TZ)
        lambda d: d.strftime("%Y-%m-%d %H:%M:%S"),               # 2026-08-15 09:47:15
        lambda d: d.isoformat(),                                 # ISO completo
        lambda d: str(int(d.timestamp())),                       # epoch unix
        lambda d: d.strftime("%d/%m/%Y %H:%M"),                  # 15/08/2026 09:47
        lambda d: d.strftime("%H:%M:%S"),                        # solo hora, sin fecha
    ])
    return fmt(base)


def garble(text, p=0.03):
    """Corrompe ocasionalmente un caracter para simular problemas de encoding."""
    chars = list(text)
    for i in range(len(chars)):
        if random.random() < p:
            chars[i] = random.choice(["�", "?", ""])
    return "".join(chars)


# ---------------------------------------------------------------------------
# Generadores de línea. TODOS reciben ctx con trace_id y lo emiten SIEMPRE,
# con nombre de campo y ubicación distinta por formato.
# ---------------------------------------------------------------------------
def fmt_syslog(ctx):
    host = random.choice(["srv-web01", "srv-web02", "web-prod-3", "PROD-APP"])
    pid = random.randint(100, 9999)
    level = random.choice(LEVELS_MESSY)
    msg = ctx["msg"]
    trace = f"{random.choice(TRACE_KEYS)}={ctx['trace_id']}"
    return f"{rand_ts_variant()} {host} {ctx['service']}[{pid}]: {level} {msg} {trace}"


def fmt_logfmt(ctx):
    level = random.choice(["info", "warn", "error", "INFO", "ERR"])
    trace = f"{random.choice(TRACE_KEYS)}={ctx['trace_id']}"
    parts = [f"time={rand_ts_variant().replace(' ', 'T')}", f"level={level}",
              f"msg=\"{ctx['msg']}\"", f"svc={ctx['service']}", trace]
    if random.random() < 0.5:
        parts.append(f"user={ctx.get('user_id', '?')}")
    random.shuffle(parts)  # el orden de los campos ni siquiera es consistente
    return " ".join(parts)


def fmt_sloppy_json(ctx):
    # JSON "casi" válido: a veces con comillas simples, comas colgantes,
    # campos faltantes o de más -> a propósito rompe el parser estándar.
    level = random.choice(LEVELS_MESSY)
    trace_key = random.choice(["trc", "trace_id", "requestId"])
    base = (f"{{'ts': '{rand_ts_variant()}', 'lvl': '{level}', "
            f"'message': '{ctx['msg']}', '{trace_key}': '{ctx['trace_id']}'")
    if random.random() < 0.6:
        base += f", 'usr': {ctx.get('user_id', 'null')}"
    if random.random() < 0.3:
        base += ","  # coma colgante
    base += "}"
    return base


def fmt_bare_print(ctx):
    level = random.choice(["DEBUG", "debug", "LOG", ">>>"])
    trace = f"{random.choice(TRACE_KEYS)}={ctx['trace_id']}"
    return f"[{level}] {ctx['service']} :: {ctx['msg']} (user {ctx.get('user_id','?')}, {trace})"


def fmt_stack_dump(ctx):
    trace = f"{random.choice(TRACE_KEYS)}={ctx['trace_id']}"
    return f"{rand_ts_variant()} {ctx['service']} ERROR {ctx['msg']} {trace} :: {STACK_TRACE}"


LINE_GENERATORS = [
    (fmt_syslog, 0.30),
    (fmt_logfmt, 0.22),
    (fmt_sloppy_json, 0.22),
    (fmt_bare_print, 0.16),
    (fmt_stack_dump, 0.10),
]


# ---------------------------------------------------------------------------
# Historias de negocio: cada una genera una transacción completa con un
# trace_id compartido por todas sus líneas (mismos escenarios que
# log_generator.py, pero escritos en frases sueltas y formatos mixtos).
# ---------------------------------------------------------------------------
def get_story(uid, trace_id):
    """Traza de una consulta GET /api/users/{id}, con algunos fallos posibles."""
    lat = lambda: random.randint(5, 900)
    roll = random.random()
    if roll < 0.06:
        steps = [
            ("api-gw", f"GET /api/users/{uid} received"),
            ("authsvc", "auth token invalido, acceso denegado"),
            ("api-gw", f"response 401 sent for user {uid} in {lat()}ms"),
        ]
    elif roll < 0.12:
        steps = [
            ("api-gw", f"GET /api/users/{uid} received"),
            ("authsvc", f"auth token check ok for {uid}"),
            ("cache", f"cache miss for user {uid}, hitting db"),
            ("db-primary", f"usuario {uid} no encontrado en base de datos"),
            ("api-gw", f"response 404 sent for user {uid} in {lat()}ms"),
        ]
    else:
        if random.random() < 0.55:
            db_step = ("cache", f"cache hit user {uid}")
        else:
            db_step = ("db-primary", f"query users table for id {uid} took {lat()}ms")
        steps = [
            ("api-gw", f"GET /api/users/{uid} received"),
            ("authsvc", f"auth token check ok for {uid}"),
            db_step,
            ("api-gw", f"response 200 sent for user {uid} in {lat()}ms"),
        ]
    return steps


def payment_story(uid, trace_id):
    """Traza de un POST /api/payments, con fallos posibles (gateway, saldo)."""
    amt = round(random.uniform(5, 2000), 2)
    pid = uuid.uuid4().hex[:8]
    score = round(random.uniform(0, 1), 2)
    roll = random.random()
    if roll < 0.07:
        steps = [
            ("payments", f"POST /api/payments recibido, monto {amt}"),
            ("payments", "body invalido: campo 'amount' faltante"),
            ("payments", f"response 400 sent in {random.randint(5, 30)}ms"),
        ]
    elif roll < 0.15:
        steps = [
            ("payments", f"payment request received amount={amt} user={uid}"),
            ("fraud-chk", f"fraud score {score} para transaccion de {uid}"),
            ("ledger", f"saldo insuficiente para cuenta de usuario {uid}"),
            ("payments", f"response 402 sent in {random.randint(20, 80)}ms"),
        ]
    elif roll < 0.24:
        steps = [
            ("payments", f"payment request received amount={amt} user={uid}"),
            ("fraud-chk", f"fraud score {score} para transaccion de {uid}"),
            ("gw-payments", "enviando request a gateway de pago externo"),
            ("gw-payments", "gateway respondio timeout despues de 5000ms"),
            ("payments", "excepcion no controlada procesando el pago: NoneType has no attribute amount"),
        ]
    else:
        steps = [
            ("payments", f"POST /api/payments recibido, monto {amt}"),
            ("fraud-chk", f"fraud score {score} para transaccion de {uid}"),
            ("gw-payments", "enviando request a gateway de pago externo"),
            ("gw-payments", f"pago autorizado id=pay_{pid}"),
            ("ledger", f"asiento contable creado para pay_{pid}"),
            ("notif-worker", f"notificacion encolada para user {uid}"),
            ("payments", f"response 200 sent in {random.randint(200, 1200)}ms"),
        ]
    return steps


def generate_trace():
    """Una transacción completa: N líneas que comparten trace_id."""
    uid = random.choice(USERS)
    trace_id = uuid.uuid4().hex[:8]
    if random.random() < 0.34:
        steps = payment_story(uid, trace_id)
    else:
        steps = get_story(uid, trace_id)

    lines = []
    gens, weights = zip(*LINE_GENERATORS)
    for service, msg in steps:
        gen = random.choices(gens, weights=weights, k=1)[0]
        ctx = {
            "msg": garble(msg, 0.02),
            "service": garble(service, 0.01),
            "user_id": uid,
            "trace_id": trace_id,
        }
        lines.append(gen(ctx))
    return lines


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generador de logs desprolijos / inconsistentes")
    parser.add_argument("--traces", type=int, default=400, help="Cantidad de transacciones (traces)")
    parser.add_argument("--output", type=str, default="/mnt/user-data/outputs/messy_logs.log")
    args = parser.parse_args()

    with open(args.output, "w", encoding="utf-8") as f:
        n_lines = 0
        for _ in range(args.traces):
            for line in generate_trace():
                f.write(line + "\n")
                n_lines += 1

    print(f"Generadas {n_lines} lineas ({args.traces} traces) de logs desprolijos en {args.output}")
    print("Todas las lineas llevan traceId compartido por transaccion")
    print("Formatos mezclados: syslog, logfmt, JSON invalido, print crudo, stack traces")


if __name__ == "__main__":
    main()
