import pytest


def test_build_prompt_marks_inferred_evidence():
    from trucha.answer import _build_prompt

    results = [{
        "trace_id": "t1",
        "summary": "Pago fallido por timeout del gateway",
        "outcome": "error",
        "services": ["payments", "gateway"],
        "levels": ["ERROR"],
        "user_id": 1788,
        "payment_id": "pay_x",
        "status_code": 503,
        "source_quality": "repaired",
        "source_path": "messy_logs.log",
        "event_count": 3,
        "vector_score": 0.9,
        "low_confidence": True,
        "causal_chain": [
            {"service": "payments", "message": "request", "confidence": 0.6},
        ],
    }]

    prompt = _build_prompt("¿por qué falló el pago?", results)

    assert "Pago fallido por timeout" in prompt
    assert "[origen: repaired]" in prompt
    assert "confianza 0.6" in prompt
    assert "INFERIDA" in prompt or "REPARADA" in prompt


class _StubProvider:
    def __init__(self, label):
        self.label = label

    async def complete(self, prompt):
        return f"stub:{self.label}"


@pytest.mark.asyncio
async def test_answer_logs_uses_provider(monkeypatch):
    import trucha.answer as answer_mod
    from trucha.config import Settings

    captured = {}

    async def fake_search(session, graph, query, settings, limit=5):
        captured["query"] = query
        return [{
            "trace_id": "t1", "summary": "s", "outcome": "ok",
            "services": [], "levels": [], "user_id": None,
            "payment_id": None, "status_code": None,
            "source_quality": "clean", "source_path": "f",
            "event_count": 1, "vector_score": 1.0,
            "low_confidence": False, "causal_chain": [],
        }]

    monkeypatch.setattr(answer_mod, "hybrid_log_search", fake_search)
    monkeypatch.setattr(
        answer_mod, "get_provider", lambda settings: _StubProvider("real")
    )

    result = await answer_mod.answer_logs(
        session=None, graph=None, question="pregunta", settings=Settings(_env_file=None)
    )

    assert captured["query"] == "pregunta"
    assert result["answer"] == "stub:real"
    assert result["provider"] == "llm"
