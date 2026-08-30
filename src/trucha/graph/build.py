"""Construcción del grafo causal a partir de trazas (funciones puras).

Cada función devuelve una lista de queries Cypher (strings) o de
operaciones (dict) que el driver de `client.py` ejecuta. Al ser puras,
se pueden testear e inspeccionar sin una instancia de Neo4j.
"""

from __future__ import annotations

from collections.abc import Iterable

# Confianza de una relación CAUSED_BY según el origen del dato.
#  - Logs limpios: causalidad explícita (caused_by) -> confianza plena.
#  - Logs desprolijos: causalidad inferida por orden temporal -> 0.6.
CONFIDENCE_EXPLICIT = 1.0
CONFIDENCE_INFERRED = 0.6


def _prep(value: str | None) -> str | None:
    return value.strip() if value else None


def trace_node_query(trace: dict) -> str:
    """Upsert del nodo Trace con su metadata de confiabilidad."""
    return (
        "MERGE (t:Trace {trace_id: $trace_id}) "
        "SET t.summary = $summary, t.outcome = $outcome, "
        "t.source_quality = $quality, t.user_id = $user_id, "
        "t.payment_id = $payment_id "
        "RETURN t"
    )


def event_node_query(event: dict) -> str:
    """Upsert del nodo LogEvent."""
    return (
        "MERGE (e:LogEvent {event_id: $event_id}) "
        "SET e.timestamp = $timestamp, e.level = $level, "
        "e.service = $service, e.message = $message, "
        "e.source_quality = $quality "
        "RETURN e"
    )


def relate_part_of_query() -> str:
    """Relación log -> traza."""
    return (
        "MATCH (e:LogEvent {event_id: $event_id}), (t:Trace {trace_id: $trace_id}) "
        "MERGE (e)-[:PART_OF]->(t)"
    )


def relate_emitted_by_query() -> str:
    """Relación log -> servicio (asegurando nodo Service)."""
    return (
        "MATCH (e:LogEvent {event_id: $event_id}) "
        "MERGE (s:Service {name: $service}) "
        "MERGE (e)-[:EMITTED_BY]->(s)"
    )


def relate_caused_by_query() -> str:
    """Relación causa-efecto entre eventos, con peso de confianza.

    La confianza se setea en la relación para que la recuperación pueda
    decidir si confía en la cadena causal o no.
    """
    return (
        "MATCH (cause:LogEvent {event_id: $cause_id}), "
        "(effect:LogEvent {event_id: $event_id}) "
        "MERGE (cause)-[r:CAUSED_BY]->(effect) "
        "SET r.confidence = $confidence"
    )


def relate_involves_query(node_label: str) -> str:
    """Relación trace -> user/payment (node_label: 'User' | 'PaymentID')."""
    return (
        "MATCH (t:Trace {trace_id: $trace_id}) "
        f"MERGE (n:{node_label} {{id: $node_id}}) "
        "MERGE (t)-[:INVOLVES]->(n)"
    )


def build_trace_operations(trace: dict, *, path: str | None = None) -> list[dict]:
    """Arma todas las operaciones Cypher para ingresar una traza al grafo.

    Devuelve una lista de dicts con las claves que entiende `GraphClient.run`:
    {query, params}. No ejecuta nada.
    """
    operations: list[dict] = []

    trace_id = trace["trace_id"]
    operations.append({
        "query": trace_node_query(trace),
        "params": {
            "trace_id": trace_id,
            "summary": trace["summary"],
            "outcome": trace.get("outcome") or "",
            "quality": trace.get("source_quality") or "clean",
            "user_id": trace.get("user_id"),
            "payment_id": _prep(trace.get("payment_id")),
        },
    })

    user_id = trace.get("user_id")
    if user_id is not None:
        operations.append({
            "query": relate_involves_query("User"),
            "params": {"trace_id": trace_id, "node_id": str(user_id)},
        })

    payment_id = _prep(trace.get("payment_id"))
    if payment_id:
        operations.append({
            "query": relate_involves_query("PaymentID"),
            "params": {"trace_id": trace_id, "node_id": payment_id},
        })

    events = trace.get("events") or []
    for event in events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        operations.append({
            "query": event_node_query(event),
            "params": {
                "event_id": event_id,
                "timestamp": event.get("timestamp"),
                "level": event.get("level"),
                "service": event.get("service"),
                "message": event.get("message"),
                "quality": event.get("source_quality") or "clean",
            },
        })
        operations.append({
            "query": relate_part_of_query(),
            "params": {"event_id": event_id, "trace_id": trace_id},
        })
        if event.get("service"):
            operations.append({
                "query": relate_emitted_by_query(),
                "params": {"event_id": event_id, "service": event["service"]},
            })
        cause_id = event.get("caused_by")
        if cause_id:
            confidence = event.get("causal_confidence") or CONFIDENCE_INFERRED
            operations.append({
                "query": relate_caused_by_query(),
                "params": {
                    "cause_id": cause_id,
                    "event_id": event_id,
                    "confidence": confidence,
                },
            })

    return operations


def build_traces_operations(traces: Iterable[dict], *, path: str | None = None) -> list[dict]:
    """Construye todas las operaciones para una colección de trazas."""
    operations: list[dict] = []
    for trace in traces:
        operations.extend(build_trace_operations(trace, path=path))
    return operations
