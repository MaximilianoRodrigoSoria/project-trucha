"""Casos de uso compartidos por la CLI y el servidor MCP."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from trucha import __version__


@dataclass(frozen=True, slots=True)
class Greeting:
    """Respuesta portable del primer caso de uso de project-trucha."""

    message: str
    agent: str
    project: str = "project-trucha"


def hello(name: str = "mundo", agent: str = "terminal") -> dict[str, str]:
    """Devuelve el saludo mínimo usado para validar cada integración."""

    clean_name = name.strip() or "mundo"
    clean_agent = agent.strip() or "terminal"
    return asdict(
        Greeting(
            message=f"Hola, {clean_name}. La memoria de project-trucha esta despierta.",
            agent=clean_agent,
        )
    )


def project_info() -> dict[str, object]:
    """Describe las capacidades que ya están disponibles en el scaffold."""

    return {
        "name": "project-trucha",
        "version": __version__,
        "status": "scaffold funcional",
        "interfaces": ["CLI", "MCP stdio"],
        "tools": ["trucha_hello", "trucha_project_info"],
        "prompts": ["hola-mundo"],
    }
