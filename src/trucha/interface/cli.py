"""Interfaz de línea de comandos de project-trucha."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        from trucha.interface.mcp import run

        return run()

    if args.command == "hola-mundo":
        print("Hola truchos, bienvenidos a project-trucha")
        return 0

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
