"""Grafo causal de logs en Neo4j (Paso 4).

Separa la *construcción* (funciones puras que arman nodos/relaciones a
partir de trazas ya normalizadas) de la *ejecución* (el cliente async del
driver Neo4j en `client.py`). Así la lógica del grafo se puede testear
sin levantar una instancia de Neo4j.
"""

from __future__ import annotations

from trucha.graph.client import GraphClient

__all__ = ["GraphClient"]
