"""Paso 6: capa de respuesta ("el rack").

Arma la respuesta en lenguaje natural a partir de la pregunta, los
resúmenes narrativos recuperados y el subgrafo causal. Con un proveedor
LLM configurado (`TRUCHA_LLM_PROVIDER`), delega en el modelo; sin él,
usa el fallback determinista que igual explica causa-raíz y cita la
confiabilidad de cada evidencia.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from trucha.config import Settings
from trucha.llm import NoneProvider, get_provider
from trucha.services import hybrid_log_search


def _format_evidence(results: list[dict]) -> str:
    """Convierte los resultados de búsqueda en un texto plano para el LLM."""
    blocks = []
    for result in results:
        levels = ", ".join(result["levels"]) or "-"
        services = ", ".join(result["services"]) or "-"
        chain = " ; ".join(
            f"{step.get('service')}: {step.get('message')}"
            f"(confianza {step.get('confidence')})"
            for step in result["causal_chain"]
        ) or "sin cadena causal"
        blocks.append(
            f"- Traza {result['trace_id']} "
            f"[origen: {result['source_quality']}] "
            f"(niveles: {levels}; servicios: {services}; "
            f"status: {result['status_code']})\n"
            f"  Resumen: {result['summary']}\n"
            f"  Cadena causal: {chain}"
        )
    return "\n".join(blocks)


def _build_prompt(question: str, results: list[dict]) -> str:
    evidence = _format_evidence(results) or "(sin evidencia recuperada)"
    return (
        "Pregunta del operador:\n"
        f"{question}\n\n"
        "Evidencia recuperada (resúmenes narrativos + cadena causal):\n"
        f"{evidence}\n\n"
        "Explicá la causa-raíz en lenguaje natural. Marcá con "
        "[INFERIDA] / [REPARADA] las piezas cuyo 'origen' no sea "
        "'clean', y citá de qué traza salió cada dato."
    )


async def answer_logs(
    session: AsyncSession,
    graph: object | None,
    question: str,
    settings: Settings,
    limit: int = 5,
) -> dict[str, object]:
    """Recupera evidencia híbrida y arma la respuesta final."""
    results = await hybrid_log_search(
        session, graph, question, settings, limit=limit
    )
    prompt = _build_prompt(question, results)
    provider = get_provider(settings)
    is_fallback = isinstance(provider, NoneProvider)
    answer = await provider.complete(prompt)
    return {
        "question": question,
        "answer": answer,
        "provider": "fallback" if is_fallback else "llm",
        "results": results,
    }
