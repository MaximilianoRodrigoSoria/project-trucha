"""Pasos 1–2: reconstrucción de causalidad y chunking por traza.

Agrupa los eventos normalizados por `trace_id` y genera un resumen
narrativo determinista de cada transacción (lo que se vectoriza y se
guarda en el grafo como nodo `Trace`).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from trucha.logs.parse import parse_file

AMOUNT_RE = re.compile(r"\b(?:amount|monto)[= ](\d+(?:\.\d+)?)\b")
STATUS_RE = re.compile(r"\bresponse (\d{3})\b")

STATUS_OUTCOMES = {
    "200": "exitoso", "201": "exitoso",
    "400": "request inválido", "401": "no autorizado",
    "402": "pago rechazado", "403": "bloqueado",
    "404": "recurso no encontrado", "429": "rate limit excedido",
    "500": "error interno", "502": "error de pasarela",
    "503": "servicio no disponible",
}
WINDOW_SECONDS = 2


def _ts_seconds(event: dict) -> float:
    return datetime.fromisoformat(event["timestamp"]).timestamp()


def infer_outcome(events: list[dict]) -> str:
    """Determina el resultado de la traza desde los mensajes o los niveles."""
    for event in reversed(events):
        match = STATUS_RE.search(event["message"])
        if match:
            return STATUS_OUTCOMES.get(match.group(1), f"status {match.group(1)}")
    levels = [event["level"] for event in events]
    if "CRITICAL" in levels or "ERROR" in levels:
        return "error"
    if "WARN" in levels:
        return "advertencia"
    return "exitoso"


def _story_type(events: list[dict]) -> str:
    text = " ".join(event["message"] for event in events).lower()
    if any(word in text for word in ("payment", "pago", "monto", "amount", "pay_")):
        return "pago"
    if any(word in text for word in ("user", "users", "usuario")):
        return "usuario"
    return "infra"


def build_summary(trace_id: str, events: list[dict]) -> str:
    """Resumen narrativo determinista de una traza (se vectoriza)."""
    outcome = infer_outcome(events)
    kind = _story_type(events)
    user = next((str(event["user_id"]) for event in events if event["user_id"]), "desconocido")
    amount = None
    for event in events:
        match = AMOUNT_RE.search(event["message"])
        if match:
            amount = match.group(1)
            break

    if kind == "pago":
        head = f"Pago {outcome} del usuario {user}"
        if amount:
            head += f" por ${amount}"
    elif kind == "usuario":
        head = f"Consulta de usuario {user} ({outcome})"
    else:
        head = f"Eventos de infraestructura ({outcome})"

    body = " ; ".join(f"{event['service']}: {event['message']}" for event in events)
    return f"Traza {trace_id}: {head}. Secuencia: {body}. Resultado: {outcome}."


def _synthetic_event_id(trace_id: str, ordinal: int, timestamp: str, message: str) -> str:
    """ID de evento sintético determinista para logs sin `event_id`.

    Los logs desprolijos no llevan un identificador de evento estable; se
    deriva uno hashando la identidad del evento (trace + posición + línea)
    para que sea reproducible en distintas corridas (idempotente en el
    grafo con MERGE) y no colisione con los IDs del log limpio.
    """
    material = f"{trace_id}|{ordinal}|{timestamp}|{message}"
    return hashlib.blake2b(material.encode("utf-8"), digest_size=6).hexdigest()[:12]


def _assign_synthetic_event_ids(events: list[dict]) -> None:
    """Da `event_id` a los eventos que no lo tienen, en orden temporal."""
    by_trace: dict[str, list[dict]] = {}
    for event in events:
        if event.get("event_id") or not event.get("trace_id"):
            continue
        by_trace.setdefault(event["trace_id"], []).append(event)
    for trace_id, group in by_trace.items():
        group.sort(key=lambda event: event["timestamp"] or "")
        for ordinal, event in enumerate(group):
            event["event_id"] = _synthetic_event_id(
                trace_id, ordinal, event.get("timestamp") or "", event.get("message") or ""
            )


def _assign_fallback_traces(events: list[dict]) -> None:
    """Solo para eventos sin trace_id: agrupa por usuario+servicio en ventana corta."""
    no_trace = [event for event in events if not event["trace_id"]]
    if not no_trace:
        return
    seen: dict[tuple, tuple[str, float]] = {}
    for event in no_trace:
        bucket_key = (event["user_id"], event["service"], int(_ts_seconds(event) / WINDOW_SECONDS))
        key, _ = seen.get(bucket_key, (f"_heuristic_{len(seen) + 1}", _ts_seconds(event)))
        seen[bucket_key] = (key, _ts_seconds(event))
        event["trace_id"] = key
        event["source_quality"] = "low_confidence"


QUALITY_RANK = {"clean": 3, "repaired": 2, "low_confidence": 1}


def _worst_quality(events: list[dict]) -> str:
    """Peor nivel de confianza entre los eventos de la traza.

    Un evento `repaired` (parsed de un log desprolijo, aunque tenga
    trace_id) o `low_confidence` degrada la traza completa: la cadena
    causal inferida no es tan confiable como una 100% `clean`.
    """
    return min(
        (event.get("source_quality", "clean") for event in events),
        key=lambda quality: QUALITY_RANK.get(quality, 0),
    )


def _resolved_caused_by(events: list[dict]) -> list[dict]:
    """Resuelve la causalidad de cada evento dentro de la traza.

    - Logs limpios: llevan `caused_by` explícito (event_id del origen).
    - Logs desprolijos: se infiere como el evento anterior de la traza
      (orden temporal), marcando el par con un peso/confianza que el
      grafo podrá usar después.
    """
    resolved = []
    previous = None
    explicit = True
    for event in events:
        if event.get("caused_by"):
            resolved.append({**event, "caused_by": event["caused_by"], "causal_confidence": 1.0})
            previous = event
            continue
        # Inferida: el evento anterior de la misma traza es su causante.
        resolved.append({
            **event,
            "caused_by": previous["event_id"] if previous else None,
            "causal_confidence": 0.6 if previous else None,
        })
        explicit = False
        previous = event
    # Si ninguna relación es explícita (traza del todo reparada) la
    # causalidad es enteramente inferida -> degradar la traza.
    if not explicit:
        for entry in resolved:
            if entry.get("causal_confidence") is None:
                entry["causal_confidence"] = 0.6
    return resolved


def traces_from_events(events: list[dict]) -> list[dict]:
    """Agrupa eventos en trazas ordenadas y les arma su resumen narrativo."""
    _assign_fallback_traces(events)
    _assign_synthetic_event_ids(events)
    by_trace: dict[str, list[dict]] = {}
    for event in events:
        by_trace.setdefault(event["trace_id"], []).append(event)

    traces = []
    for trace_id, trace_events in by_trace.items():
        trace_events.sort(key=lambda event: event["timestamp"])
        user_id = next((event["user_id"] for event in trace_events if event["user_id"]), None)
        payment_id = next((event["payment_id"] for event in trace_events if event["payment_id"]), None)
        quality = _worst_quality(trace_events)
        traced = _resolved_caused_by(trace_events)
        traces.append({
            "trace_id": trace_id,
            "events": traced,
            "summary": build_summary(trace_id, trace_events),
            "outcome": infer_outcome(trace_events),
            "user_id": user_id,
            "payment_id": payment_id,
            "source_quality": quality,
            "has_low_confidence": quality in ("repaired", "low_confidence"),
        })
    return traces


def load_traces(path: str | Path) -> list[dict]:
    """Atajo CLI: parsea un archivo y devuelve las trazas ya resumidas."""
    events = parse_file(Path(path))
    return traces_from_events(events)
