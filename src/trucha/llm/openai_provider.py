"""Provider OpenAI opt-in para la capa de respuesta (Paso 6)."""

from __future__ import annotations

from trucha.llm import LLMProvider


class OpenAIProvider(LLMProvider):
    """Usa el cliente OpenAI de forma diferida (no se requiere opcional)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"

    async def complete(self, prompt: str) -> str:
        # Import diferido: openai es dependencia opcional.
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un analista de observabilidad. Explica causa-raíz "
                    "y cita si cada dato viene de logs limpios, reparados o inferidos.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
