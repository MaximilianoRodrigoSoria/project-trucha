"""Interfaz de línea de comandos de project-trucha."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from trucha.config import get_settings
from trucha.core import hello, project_info


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trucha",
        description="Memoria local-first para agentes de código.",
    )
    parser.add_argument("--json", action="store_true", help="imprime JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    hello_parser = commands.add_parser("hello", help="prueba la instalación")
    hello_parser.add_argument("name", nargs="?", default="mundo")
    hello_parser.add_argument("--agent", default="terminal")
    commands.add_parser("info", help="muestra capacidades disponibles")
    commands.add_parser("hola-mundo", help="muestra la bienvenida del proyecto")
    commands.add_parser("mcp", help="inicia el servidor MCP por stdio")

    logs = commands.add_parser("logs", help="ingesta y recuperación híbrida de logs")
    logs_sub = logs.add_subparsers(dest="logs_command", required=True)

    ingest = logs_sub.add_parser("ingest", help="parsea logs y guarda trazas vectorizadas (Paso 0-3)")
    ingest.add_argument("paths", nargs="+", type=Path, help="archivos .jsonl / .log")
    ingest.add_argument("--graph", action="store_true", help="también escribe el grafo causal en Neo4j (Paso 4)")

    search = logs_sub.add_parser("search", help="recuperación híbrida por similitud semántica + grafo (Paso 5)")
    search.add_argument("query", help="pregunta en lenguaje natural")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--graph", action="store_true", help="expandir cadena causal desde Neo4j")

    answer = logs_sub.add_parser("answer", help="capa de respuesta con LLM (Paso 6, 'el rack')")
    answer.add_argument("query", help="pregunta en lenguaje natural")
    answer.add_argument("--limit", type=int, default=5)
    answer.add_argument("--graph", action="store_true", help="usar cadena causal desde Neo4j")

    return parser


def _print_payload(payload: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        print(payload)


def _run_logs(args: argparse.Namespace, as_json: bool) -> int:
    settings = get_settings()
    from trucha.store.database import SessionFactory

    if args.logs_command == "ingest":
        async def _ingest() -> dict[str, int]:
            async with SessionFactory() as session:
                from trucha.services import ingest_logs

                stats = await ingest_logs(session, args.paths, settings)
                if args.graph:
                    await _sync_graph(args.paths, settings)
                return stats

        result = asyncio.run(_ingest())
    elif args.logs_command == "search":
        async def _search() -> list:
            async with SessionFactory() as session:
                from trucha.graph.client import open_graph
                from trucha.services import hybrid_log_search

                graph = await open_graph(settings) if args.graph else None
                try:
                    return await hybrid_log_search(session, graph, args.query, settings, limit=args.limit)
                finally:
                    if graph is not None:
                        await graph.close()

        result = asyncio.run(_search())
    else:  # answer
        async def _answer() -> dict:
            async with SessionFactory() as session:
                from trucha.answer import answer_logs
                from trucha.graph.client import open_graph

                graph = await open_graph(settings) if args.graph else None
                try:
                    return await answer_logs(session, graph, args.query, settings, limit=args.limit)
                finally:
                    if graph is not None:
                        await graph.close()

        result = asyncio.run(_answer())

    _print_payload(result, as_json)
    return 0


async def _sync_graph(paths: list[Path], settings) -> None:
    """Escribe el grafo causal en Neo4j para todas las trazas de los paths."""
    from trucha.graph.client import open_graph
    from trucha.logs.trace import load_traces

    graph = await open_graph(settings)
    try:
        for path in paths:
            traces = load_traces(path)
            await graph.sync_traces(traces)
    finally:
        await graph.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        from trucha.interface.mcp import run

        return run()

    if args.command == "hola-mundo":
        print("Hola truchos, bienvenidos a project-trucha")
        return 0

    if args.command == "logs":
        return _run_logs(args, args.json)

    result = (
        hello(name=args.name, agent=args.agent)
        if args.command == "hello"
        else project_info()
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif args.command == "hello":
        print(result["message"])
        print(f"Agente: {result['agent']}")
    else:
        print(f"{result['name']} {result['version']} · {result['status']}")
        print("Interfaces: " + ", ".join(result["interfaces"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
