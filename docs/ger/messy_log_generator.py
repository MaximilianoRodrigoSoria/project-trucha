"""
messy_log_generator.py
=======================
Contraparte "sucia" de log_generator.py.

Simula cómo son los logs en la mayoría de los sistemas reales: sin
estándar, mezclando formatos, con campos faltantes, timestamps
inconsistentes, niveles mal escritos, stack traces crudos pegados en
una sola línea gigante, líneas corruptas, texto en dos idiomas, etc.

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


def rand_id_maybe():
    """A veces hay trace/request id, a veces no, y con nombres de campo distintos."""
    if random.random() < 0.35:
        return None
    key = random.choice(["reqId", "request_id", "trace", "rid", "corrId"])
    return f"{key}={uuid.uuid4().hex[:8]}"


def garble(text, p=0.03):
    """Corrompe ocasionalmente un caracter para simular problemas de encoding."""
    chars = list(text)
    for i in range(len(chars)):
        if random.random() < p:
            chars[i] = random.choice(["�", "?", ""])
    return "".join(chars)


# ---------------------------------------------------------------------------
# Generadores de línea, cada uno con un formato distinto
# ---------------------------------------------------------------------------
def fmt_syslog(ctx):
    host = random.choice(["srv-web01", "srv-web02", "web-prod-3", "PROD-APP"])
    pid = random.randint(100, 9999)
    level = random.choice(LEVELS_MESSY)
    msg = ctx["msg"]
    return f"{rand_ts_variant()} {host} {ctx['service']}[{pid}]: {level} {msg}"


def fmt_logfmt(ctx):
    level = random.choice(["info", "warn", "error", "INFO", "ERR"])
    parts = [f"time={rand_ts_variant().replace(' ', 'T')}", f"level={level}",
              f"msg=\"{ctx['msg']}\"", f"svc={ctx['service']}"]
    if random.random() < 0.5:
        parts.append(f"user={ctx.get('user_id', '?')}")
    rid = rand_id_maybe()
    if rid:
        parts.append(rid)
    random.shuffle(parts)  # el orden de los campos ni siquiera es consistente
    return " ".join(parts)


def fmt_sloppy_json(ctx):
    # JSON "casi" válido: a veces con comillas simples, comas colgantes,
    # campos faltantes o de más -> a propósito rompe el parser estándar.
    level = random.choice(LEVELS_MESSY)
    base = f"{{'ts': '{rand_ts_variant()}', 'lvl': '{level}', 'message': '{ctx['msg']}'"
    if random.random() < 0.6:
        base += f", 'usr': {ctx.get('user_id', 'null')}"
    if random.random() < 0.3:
        base += ","  # coma colgante
    base += "}"
    return base


def fmt_bare_print(ctx):
    level = random.choice(["DEBUG", "debug", "LOG", ">>>"])
    return f"[{level}] {ctx['service']} :: {ctx['msg']} (user {ctx.get('user_id','?')})"


def fmt_stack_dump(ctx):
    return f"{rand_ts_variant()} {ctx['service']} ERROR {ctx['msg']} :: {STACK_TRACE}"


def fmt_noise(ctx):
    """Basura pura: líneas truncadas, con encoding roto, o vacías de contenido útil."""
    options = [
        "",
        "----",
        "connection reset by peer",
        garble(f"{ctx['service']} restart", p=0.25),
        f"{rand_ts_variant()} ...",
        f"WARNING WARNING WARNING low disk",
        "null",
        "{}",
    ]
    return random.choice(options)


LINE_GENERATORS = [
    (fmt_syslog, 0.28),
    (fmt_logfmt, 0.20),
    (fmt_sloppy_json, 0.20),
    (fmt_bare_print, 0.15),
    (fmt_stack_dump, 0.07),
    (fmt_noise, 0.10),
]


# ---------------------------------------------------------------------------
# Contenido: mismos escenarios de negocio que log_generator.py, pero
# escritos en frases sueltas, a veces en español, a veces en inglés,
# sin ningún campo estructurado obligatorio.
# ---------------------------------------------------------------------------
GET_USER_MESSAGES = [
    "GET /api/users/{uid} received",
    "solicitud de usuario {uid} recibida",
    "cache miss for user {uid}, hitting db",
    "cache hit user {uid}",
    "query users table for id {uid} took {lat}ms",
    "usuario {uid} no encontrado en base de datos",
    "auth token check ok for {uid}",
    "auth token invalido, acceso denegado",
    "response 200 sent for user {uid} in {lat}ms",
    "db connection pool casi lleno, 48/50",
    "timeout consultando db para usuario {uid}",
    "unexpected error processing request /api/users/{uid}",
]

PAYMENT_MESSAGES = [
    "POST /api/payments recibido, monto {amt}",
    "payment request received amount={amt} user={uid}",
    "fraud score {score} para transaccion de {uid}",
    "saldo insuficiente para cuenta de usuario {uid}",
    "enviando request a gateway de pago externo",
    "gateway respondio timeout despues de 5000ms",
    "pago autorizado id=pay_{pid}",
    "pago rechazado por el emisor",
    "asiento contable creado para pay_{pid}",
    "notificacion encolada para user {uid}",
    "worker no pudo consumir mensaje de la cola, reintentando",
    "excepcion no controlada procesando el pago: NoneType has no attribute amount",
]


def build_ctx():
    scenario = random.choice(["get", "get", "payment"])  # un poco más de trafico GET
    uid = random.choice(USERS)
    if scenario == "get":
        msg = random.choice(GET_USER_MESSAGES).format(uid=uid, lat=random.randint(5, 900))
        service = random.choice(["api-gw", "authsvc", "cache", "db-primary"])
    else:
        msg = random.choice(PAYMENT_MESSAGES).format(
            uid=uid, amt=round(random.uniform(5, 2000), 2),
            score=round(random.uniform(0, 1), 2), pid=uuid.uuid4().hex[:8])
        service = random.choice(["payments", "fraud-chk", "ledger", "notif-worker", "gw-payments"])
    return {"msg": msg, "service": service, "user_id": uid}


def generate_line():
    gens, weights = zip(*LINE_GENERATORS)
    gen = random.choices(gens, weights=weights, k=1)[0]
    ctx = build_ctx()
    return gen(ctx)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generador de logs desprolijos / inconsistentes")
    parser.add_argument("--lines", type=int, default=2000)
    parser.add_argument("--output", type=str, default="/mnt/user-data/outputs/messy_logs.log")
    args = parser.parse_args()

    with open(args.output, "w", encoding="utf-8") as f:
        for _ in range(args.lines):
            f.write(generate_line() + "\n")

    print(f"Generadas {args.lines} lineas de logs desprolijos en {args.output}")
    print("Formatos mezclados: syslog, logfmt, JSON invalido, print crudo, stack traces, ruido")


if __name__ == "__main__":
    main()
