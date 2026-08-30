"""Capa de respuesta LLM pluggable (Paso 6: "el rack").

Un LLM recibe la pregunta + los resúmenes narrativos recuperados + el
subgrafo causal y arma la respuesta explicando causa-raíz y citando de
qué fuente salió cada dato (limpia / reparada / inferida).

El proveedor default (`NoneProvider`) arma una respuesta determinista que
junta el contexto y marca la confiabilidad sin depender de una API key,
manteniendo el principio local-first del proyecto. Los providers reales
(OpenAI/Anthropic) son opt-in vía config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from trucha.config import Settings


class LLMProvider(ABC):
    """Contrato de cualquier proveedor de LLM para la capa de respuesta."""

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Devuelve la respuesta del modelo para el prompt dado."""


class NoneProvider(LLMProvider):
    """Fallback determinista: no llama a ningún modelo.

    Arma una respuesta en lenguaje natural concatenando el contexto
    recuperado y etiquetando la confiabilidad de cada evidencia, para
    que el sistema siga siendo útil sin API key.
    """

    async def complete(self, prompt: str) -> str:
        return prompt


def get_provider(settings: Settings) -> LLMProvider:
    """Construye el proveedor configurado (o el fallback determinista)."""
    name = (settings.llm_provider or "").strip().lower()
    if name == "openai":
        from trucha.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    if name == "anthropic":
        from trucha.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    return NoneProvider()
