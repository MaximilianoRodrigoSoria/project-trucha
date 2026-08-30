from datetime import UTC, datetime


def _event(event_id, trace_id, service, message, level="INFO",
           source_quality="clean", caused_by=None, user_id=None, payment_id=None):
    return {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "trace_id": trace_id,
        "event_id": event_id,
        "caused_by": caused_by,
        "service": service,
        "level": level,
        "message": message,
        "user_id": user_id,
        "payment_id": payment_id,
        "metadata": {},
        "source_quality": source_quality,
        "timestamp_inferred": False,
    }


def test_clean_trace_keeps_explicit_causality_with_full_confidence():
    from trucha.logs.trace import traces_from_events

    events = [
        _event("a", "trc1", "api-gateway", "request", caused_by=None),
        _event("b", "trc1", "auth-service", "validated", caused_by="a"),
        _event("c", "trc1", "api-gateway", "response", caused_by="b"),
    ]
    trace, = traces_from_events(events)

    assert trace["source_quality"] == "clean"
    assert trace["has_low_confidence"] is False
    assert all(ev["causal_confidence"] == 1.0 for ev in trace["events"] if ev["caused_by"])


def test_repaired_trace_degrades_quality_even_with_trace_id():
    from trucha.logs.trace import traces_from_events

    events = [
        _event("a", "trc2", "api-gw", "request", source_quality="repaired"),
        _event("b", "trc2", "authsvc", "validated", source_quality="repaired"),
    ]
    trace, = traces_from_events(events)

    assert trace["source_quality"] == "repaired"
    assert trace["has_low_confidence"] is True


def test_repaired_trace_infers_causality_between_lines():
    from trucha.logs.trace import traces_from_events

    events = [
        _event("a", "trc3", "api-gw", "request", source_quality="repaired"),
        _event("b", "trc3", "gw-payments", "gateway ok", source_quality="repaired"),
    ]
    trace, = traces_from_events(events)

    second = trace["events"][1]
    assert second["caused_by"] == "a"
    assert second["causal_confidence"] == 0.6


def test_repaired_events_without_event_id_get_synthetic_deterministic_ids():
    from trucha.logs.trace import traces_from_events

    events = [
        _event(None, "trc5", "api-gw", "request", source_quality="repaired"),
        _event(None, "trc5", "gw-payments", "gateway ok", source_quality="repaired"),
    ]
    trace, = traces_from_events(events)

    ids = [ev["event_id"] for ev in trace["events"]]
    assert all(ids), "event_id sintético no puede ser None"
    assert len(set(ids)) == 2, "IDs sintéticos deben ser únicos dentro de la traza"
    # Determinista: reproducir el parseo da los mismos IDs.
    again, = traces_from_events([
        _event(None, "trc5", "api-gw", "request", source_quality="repaired"),
        _event(None, "trc5", "gw-payments", "gateway ok", source_quality="repaired"),
    ])
    assert [ev["event_id"] for ev in again["events"]] == ids
    # La causalidad inferida ahora apunta a IDs válidos.
    second = trace["events"][1]
    assert second["caused_by"] == ids[0]
    assert second["causal_confidence"] == 0.6


def test_mixed_quality_uses_worst_and_marked_low_confidence():
    from trucha.logs.trace import traces_from_events

    events = [
        _event("a", "trc4", "api-gateway", "request", caused_by=None, source_quality="clean"),
        _event("b", "trc4", "authsvc", "weird", source_quality="low_confidence"),
    ]
    trace, = traces_from_events(events)

    assert trace["source_quality"] == "low_confidence"
    assert trace["has_low_confidence"] is True
