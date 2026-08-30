"""Cliente async del driver Neo4j (Paso 4: ejecución del grafo).

Envuelve `AsyncGraphDatabase` con métodos de alto nivel: `sync_trace`,
`sync_traces` (aplican las operaciones construidas por `build.py`) y
`causal_chain` (recupera la cadena causal completa de una traza para el
Paso 5).
"""

from __future__ import annotations

from collections.abc import Iterable

from trucha.graph.build import build_traces_operations


class GraphClient:
    """Cliente Neo4j reutilizable para el grafo causal de logs."""

    def __init__(self, driver) -> None:
        self.driver = driver

    @classmethod
    def connect(cls, uri: str, user: str, password: str) -> GraphClient:
        from neo4j import AsyncGraphDatabase

        return cls(AsyncGraphDatabase.driver(uri, auth=(user, password)))

    async def close(self) -> None:
        await self.driver.close()

    async def _run(self, query: str, params: dict) -> None:
        async with self.driver.session() as session:
            await session.run(query, params)

    async def sync_trace(self, trace: dict) -> list[str]:
        """Ingresa una traza al grafo. Devuelve los IDs de eventos creados."""
        from trucha.graph.build import build_trace_operations

        operations = build_trace_operations(trace)
        event_ids: list[str] = []
        async with self.driver.session() as session:
            for operation in operations:
                await session.run(operation["query"], operation["params"])
            for event in trace.get("events") or []:
                if event.get("event_id"):
                    event_ids.append(event["event_id"])
        return event_ids

    async def sync_traces(self, traces: Iterable[dict]) -> int:
        """Ingresa una colección de trazas en una única transacción."""
        traces = list(traces)
        operations = build_traces_operations(traces)

        async def _apply(tx) -> None:
            for op in operations:
                await tx.run(op["query"], op["params"])

        async with self.driver.session() as session:
            await session.execute_write(_apply)
        return len(traces)

    async def causal_chain(
        self, trace_id: str, *, max_depth: int = 10
    ) -> list[dict]:
        """Recupera la cadena causal completa de una traza (Paso 5).

        Expande las relaciones CAUSED_BY entre eventos de la traza en
        orden temporal, e informa la confianza de cada eslabón.
        """
        query = (
            "MATCH (t:Trace {trace_id: $trace_id})<-[:PART_OF]-"
            "(e:LogEvent)<-[r:CAUSED_BY]-(cause:LogEvent) "
            "RETURN cause.event_id AS cause_id, e.event_id AS event_id, "
            "e.service AS service, e.level AS level, e.message AS message, "
            "e.timestamp AS timestamp, r.confidence AS confidence, "
            "e.source_quality AS source_quality "
            "ORDER BY timestamp"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"trace_id": trace_id})
            records = await result.data()
        return records


async def open_graph(settings) -> GraphClient:
    """Abre un GraphClient desde settings."""
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    return GraphClient(driver)
