"""Servidor MCP mínimo y sin dependencias, transportado por stdio."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from trucha import __version__
from trucha.core import hello, project_info

PROTOCOL_VERSION = "2025-06-18"
INSTRUCTIONS = (
    "project-trucha ofrece memoria local para agentes. En este scaffold usa "
    "trucha_hello para comprobar la conexión y trucha_project_info para conocer "
    "las capacidades disponibles. No ejecuta comandos ni accede a la red."
)

TOOLS = [
    {
        "name": "trucha_hello",
        "title": "Saludar desde project-trucha",
        "description": "Valida la conexión devolviendo un saludo y el agente origen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Persona a saludar"},
                "agent": {"type": "string", "description": "Codex, Claude u OpenCode"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "trucha_project_info",
        "title": "Ver estado de project-trucha",
        "description": "Devuelve versión, interfaces y herramientas disponibles.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _result(payload: dict[str, object]) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    """Procesa una petición JSON-RPC de MCP."""

    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        return None

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "project-trucha", "version": __version__},
            "instructions": INSTRUCTIONS,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params") or {}
        arguments = params.get("arguments") or {}
        tool_name = params.get("name")
        if tool_name == "trucha_hello":
            result = _result(
                hello(
                    name=str(arguments.get("name", "mundo")),
                    agent=str(arguments.get("agent", "MCP")),
                )
            )
        elif tool_name == "trucha_project_info":
            result = _result(project_info())
        else:
            return _error(request_id, -32602, f"Herramienta desconocida: {tool_name}")
    else:
        return _error(request_id, -32601, f"Método no soportado: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def serve(input_stream: TextIO, output_stream: TextIO) -> None:
    """Lee un objeto JSON-RPC por línea y responde por stdout."""

    for raw_line in input_stream:
        if not raw_line.strip():
            continue
        try:
            response = handle(json.loads(raw_line))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            response = _error(None, -32700, f"JSON inválido: {exc}")
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()


def run() -> int:
    serve(sys.stdin, sys.stdout)
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
