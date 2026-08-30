import pytest


class _Row:
    def __init__(self, trace, distance):
        self._trace = trace
        self._distance = distance

    def __getitem__(self, index):
        return (self._trace, self._distance)[index]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_hybrid_log_search_marks_low_confidence_and_fetches_chain(monkeypatch):
    from trucha import services
    from trucha.config import Settings

    settings = Settings(_env_file=None, embedding_dimensions=16)

    # Objeto con atributos, como devuelve el ORM.
    class FakeTrace:
        trace_id = "trc-x"
        summary = "Pago fallido por timeout del gateway"
        outcome = "error"
        services = ("payments", "gateway")
        levels = ("ERROR",)
        user_id = 1788
        payment_id = "pay_1"
        status_code = 503
        source_quality = "repaired"
        source_path = "messy_logs.log"
        event_count = 3

    class _Session:
        async def execute(self, statement):
            return _Result([_Row(FakeTrace(), 0.2)])

    graph_calls = []

    class _Graph:
        async def causal_chain(self, trace_id):
            graph_calls.append(trace_id)
            return [{"service": "payments", "message": "request", "confidence": 0.6}]

    result = await services.hybrid_log_search(
        _Session(), _Graph(), "pago fallido", settings, limit=5
    )

    assert len(result) == 1
    hit = result[0]
    assert hit["trace_id"] == "trc-x"
    assert hit["source_quality"] == "repaired"
    assert hit["low_confidence"] is True
    assert hit["causal_chain"][0]["confidence"] == 0.6
    assert graph_calls == ["trc-x"]


@pytest.mark.asyncio
async def test_hybrid_log_search_without_graph_returns_chain_empty():
    from trucha import services
    from trucha.config import Settings

    settings = Settings(_env_file=None, embedding_dimensions=16)

    class FakeTrace:
        trace_id = "trc-y"
        summary = "s"
        outcome = "ok"
        services = ()
        levels = ()
        user_id = None
        payment_id = None
        status_code = None
        source_quality = "clean"
        source_path = "f"
        event_count = 1

    class _Session:
        async def execute(self, statement):
            return _Result([_Row(FakeTrace(), 0.1)])

    result = await services.hybrid_log_search(
        _Session(), None, "consulta", settings, limit=5
    )

    assert result[0]["causal_chain"] == []
    assert result[0]["low_confidence"] is False
