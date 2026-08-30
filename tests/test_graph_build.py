def _make_trace(trace_id, events):
    return {
        "trace_id": trace_id,
        "events": events,
        "summary": f"Traza {trace_id}",
        "outcome": "exitoso",
        "user_id": 1788,
        "payment_id": "pay_12345678",
        "source_quality": "repaired",
    }


def _event(event_id, cause=None, confidence=None, quality="repaired"):
    return {
        "event_id": event_id,
        "timestamp": "2026-08-16T00:00:00+00:00",
        "level": "INFO",
        "service": "api-gw",
        "message": "request",
        "caused_by": cause,
        "causal_confidence": confidence,
        "source_quality": quality,
    }


def test_build_creates_trace_and_involves_nodes():
    from trucha.graph.build import build_trace_operations

    trace = _make_trace("trc1", [_event("a"), _event("b", cause="a", confidence=0.6)])
    ops = build_trace_operations(trace)

    # trace + 2 involves (user, payment) + 2 eventos + 2 part_of
    # + 2 emitted_by + 1 caused_by
    assert len(ops) == 10

    assert any("INVOLVES" in op["query"] and "User" in op["query"] for op in ops)
    assert any("INVOLVES" in op["query"] and "PaymentID" in op["query"] for op in ops)
    assert sum("PART_OF" in op["query"] for op in ops) == 2
    assert sum("EMITTED_BY" in op["query"] for op in ops) == 2
    assert sum("CAUSED_BY" in op["query"] for op in ops) == 1


def test_inferred_causality_carries_confidence_weight():
    from trucha.graph.build import (
        CONFIDENCE_INFERRED,
        build_trace_operations,
        relate_caused_by_query,
    )

    trace = _make_trace("trc2", [_event("a"), _event("b", cause="a", confidence=0.6)])
    ops = build_trace_operations(trace)

    caused = [op for op in ops if "CAUSED_BY" in op["query"]]
    assert len(caused) == 1
    assert caused[0]["params"]["confidence"] == CONFIDENCE_INFERRED
    assert caused[0]["params"]["cause_id"] == "a"
    assert caused[0]["params"]["event_id"] == "b"
    assert "r.confidence = $confidence" in relate_caused_by_query()
