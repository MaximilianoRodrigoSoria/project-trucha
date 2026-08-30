"""Provider Anthropic opt-in para la capa de respuesta (Paso 6)."""

from __future__ import annotations

from trucha.llm import LLMProvider


class AnthropicProvider(LLMProvider):
    """Usa el cliente Anthropic de forma diferida (dependencia opcional)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or "claude-3-5-haiku-latest"

    async def complete(self, prompt: str) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key)
        message = await client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "Eres un analista de observabilidad. Explica causa-raíz y cita "
                "si cada dato viene de logs limpios, reparados o inferidos."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ).strip()
