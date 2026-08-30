"""Paso 0: parseo y reparación de logs (cascada de parsers + normalización).

Toma una línea de `messy_logs.log` (o un objeto JSON de `logs.jsonl`) y la
convierte al schema unificado:
  timestamp, trace_id, event_id, caused_by, service, level, message,
  user_id, payment_id, metadata, source_quality, timestamp_inferred

Los logs limpios entran por `json.loads` directo (source_quality="clean").
Los desprolijos pasan por la cascada: sloppy JSON → bare print → stack dump
→ syslog → logfmt. Si nada matchea, la línea se descarta (None).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Catálogos de normalización
# ---------------------------------------------------------------------------
TRACE_KEYS = ("reqId", "request_id", "trace", "rid", "corrId", "tid", "trace_id", "trc", "requestId")
TRACE_KV_RE = re.compile(rf"\b(?:{'|'.join(TRACE_KEYS)})=([0-9a-fA-F]+)")

LEVEL_SYNONYMS = {
    "info": "INFO", "infoo": "INFO", "log": "INFO", "inf": "INFO",
    "warn": "WARN", "warning": "WARN", "warn": "WARN",
    "error": "ERROR", "err": "ERROR", "errr": "ERROR",
    "critical": "CRITICAL", "crit": "CRITICAL",
    "debug": "DEBUG", ">>>": "DEBUG", "trace": "DEBUG",
}

SERVICE_MAP = {
    "api-gw": "api-gateway", "GATEWAY": "api-gateway",
    "authsvc": "auth-service",
    "cache": "cache-service",
    "db-primary": "db-service",
    "payments": "payments-service",
    "fraud-chk": "fraud-service",
    "ledger": "ledger-service",
    "notif-worker": "notification-worker",
    "gw-payments": "payment-gateway",
}

_MONTHS = {name: num for num, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

# ---------------------------------------------------------------------------
# RegEx por formato
# ---------------------------------------------------------------------------
SYSLOG_RE = re.compile(
    r"^(?P<ts>.+?)\s+(?P<host>srv-web01|srv-web02|web-prod-3|PROD-APP)\s+"
    r"(?P<svc>\S+?)\[(?P<pid>\d+)\]:\s+(?P<lvl>\S+)\s+"
    r"(?P<msg>.+?)(?:\s+(?P<trace_kv>\w+=[0-9a-fA-F]+))?$"
)
_LEVEL_WORDS = r"(?:INFO|info|Info|WARN|warning|Warning|Warn|ERROR|error|Err|ERR|CRITICAL|crit|DEBUG|debug|trace|LOG|>>>)"
STACK_RE = re.compile(
    rf"^(?P<ts>.+?)\s+(?P<svc>\S+)\s+(?P<lvl>{_LEVEL_WORDS})\s+"
    r"(?P<msg>.*?)\s+(?P<trace_kv>\w+=[0-9a-fA-F]+)\s*::\s+Traceback.*$"
)
BARE_RE = re.compile(
    r"^\[(?P<lvl>[^\]]+)\]\s+(?P<svc>\S+)\s+::\s+"
    r"(?P<msg>.*?)\s+\(user\s+(?P<user>\d+),\s+(?P<trace_kv>\w+=[0-9a-fA-F]+)\)$"
)
SLOPPY_RE = re.compile(
    r"^\{\s*'ts':\s*'(?P<ts>.*?)'\s*,\s*'lvl':\s*'(?P<lvl>.*?)'\s*,\s*"
    r"'message':\s*'(?P<msg>.*)'\s*,\s*'(?P<trace_k>trc|trace_id|requestId)':\s*'(?P<trace_v>[0-9a-fA-F]+)'\s*"
    r"(?:,\s*'usr':\s*(?P<usr>\d+|null))?\s*,?\s*\}$"
)

USER_RE = re.compile(
    r"user(?:=|s/|/|\s+)(\d{3,5})\b"
    r"|\bpara\s+user\s+(\d{3,5})\b"
    r"|\bde\s+(\d{3,5})\b"
    r"|\bfor\s+id\s+(\d{3,5})\b"
    r"|\bfor\s+(\d{3,5})\b"
    r"|\busuario\s+(\d{3,5})\b"
)
PAYMENT_RE = re.compile(r"\bpay_[0-9a-f]{8}\b")


def normalize_level(level: str) -> str:
    return LEVEL_SYNONYMS.get(level.strip().lower(), level.strip().upper() or "INFO")


def normalize_service(service: str) -> str:
    return SERVICE_MAP.get(service, service)


def parse_timestamp(value: str, ingested_at: datetime) -> tuple[str | None, bool]:
    """Normaliza a ISO 8601 UTC. Devuelve (timestamp, timestamp_inferred)."""
    value = value.strip()
    if not value:
        return None, False

    m = re.fullmatch(r"(\w{3})T(\d{2})T(\d{2}):(\d{2}):(\d{2})", value)   # logfmt: AugT16T04:20:18
    if m:
        value = f"{m[1]} {m[2]} {m[3]}:{m[4]}:{m[5]}"
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})T(\d{2}):(\d{2})", value)  # logfmt: 16/08/2026T06:10
    if m:
        value = f"{m[1]}/{m[2]}/{m[3]} {m[4]}:{m[5]}"

    if re.fullmatch(r"\d{9,}", value):  # epoch unix
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat(timespec="milliseconds"), False

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    else:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC).isoformat(timespec="milliseconds"), True
        return dt.astimezone(UTC).isoformat(timespec="milliseconds"), False

    m = re.fullmatch(r"(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})", value)  # Aug 15 09:47:15
    if m and (month := _MONTHS.get(m[1].lower())):
        dt = datetime(ingested_at.year, month, int(m[2]), int(m[3]), int(m[4]), int(m[5]))
        return dt.replace(tzinfo=UTC).isoformat(timespec="milliseconds"), True

    for fmt, has_year in (("%d/%m/%Y %H:%M", True), ("%Y-%m-%d %H:%M:%S", True), ("%H:%M:%S", False)):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if not has_year:
            dt = dt.replace(year=ingested_at.year)
        return dt.replace(tzinfo=UTC).isoformat(timespec="milliseconds"), not has_year
    return None, False


def _extract_user(message: str) -> int | None:
    for match in USER_RE.finditer(message):
        value = next((group for group in match.groups() if group), None)
        if value:
            return int(value)
    return None


def _extract_payment(message: str) -> str | None:
    match = PAYMENT_RE.search(message)
    return match.group(0) if match else None


def _base(ts: str | None, inferred: bool, trace_id: str | None, service: str,
          level: str, message: str, quality: str, user_id: int | None = None,
          payment_id: str | None = None, event_id: str | None = None,
          caused_by: str | None = None, metadata: dict | None = None) -> dict:
    return {
        "timestamp": ts,
        "trace_id": trace_id,
        "event_id": event_id,
        "caused_by": caused_by,
        "service": service,
        "level": level,
        "message": message,
        "user_id": user_id,
        "payment_id": payment_id,
        "metadata": metadata or {},
        "source_quality": quality,
        "timestamp_inferred": inferred,
    }


def _from_clean(obj: dict) -> dict:
    metadata = obj.get("metadata") or {}
    return _base(
        ts=obj.get("timestamp"), inferred=False, trace_id=obj.get("trace_id"),
        service=normalize_service(obj.get("service", "")),
        level=normalize_level(obj.get("level", "INFO")),
        message=obj.get("message", ""), quality="clean",
        user_id=metadata.get("user_id"), payment_id=metadata.get("payment_id"),
        event_id=obj.get("event_id"), caused_by=obj.get("caused_by"), metadata=metadata,
    )


def _from_parts(ts_raw: str | None, service: str, level: str, message: str,
                trace_id: str | None, ingested_at: datetime, quality: str = "repaired",
                user_id: int | None = None) -> dict | None:
    if ts_raw:
        ts, inferred = parse_timestamp(ts_raw, ingested_at)
        if not ts:
            return None
    else:
        ts, inferred = ingested_at.astimezone(UTC).isoformat(timespec="milliseconds"), True
    return _base(
        ts=ts, inferred=inferred, trace_id=trace_id,
        service=normalize_service(service), level=normalize_level(level),
        message=message, quality=quality,
        user_id=user_id or _extract_user(message),
        payment_id=_extract_payment(message),
    )


def _from_logfmt(line: str, ingested_at: datetime) -> dict | None:
    parts: list[str] = []
    buffer, in_quotes = "", False
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif char.isspace() and not in_quotes:
            if buffer:
                parts.append(buffer)
                buffer = ""
            continue
        buffer += char
    if buffer:
        parts.append(buffer)

    fields: dict[str, str] = {}
    for token in parts:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value.strip('"')

    trace_id = next((fields[key] for key in TRACE_KEYS if key in fields), None)
    if trace_id is None or "msg" not in fields or "svc" not in fields:
        return None
    return _from_parts(
        fields.get("time"), fields.get("svc", ""), fields.get("level", ""),
        fields["msg"], trace_id, ingested_at,
        user_id=int(fields["user"]) if fields.get("user", "").isdigit() else None,
    )


def parse_line(line: str, ingested_at: datetime | None = None) -> dict | None:
    """Convierte una línea de log (prolija o desprolija) al schema unificado."""
    ingested_at = ingested_at or datetime.now(UTC)
    line = line.strip()
    if not line:
        return None

    try:
        obj = json.loads(line)
    except ValueError:
        obj = None
    if isinstance(obj, dict) and ("log_type" in obj or "trace_id" in obj):
        return _from_clean(obj)

    match = SLOPPY_RE.match(line)
    if match:
        return _from_parts(
            match["ts"], "unknown", match["lvl"], match["msg"], match["trace_v"],
            ingested_at,
            user_id=int(match["usr"]) if match["usr"] and match["usr"].isdigit() else None,
        )

    match = BARE_RE.match(line)
    if match:
        trace_kv = TRACE_KV_RE.search(match["trace_kv"])
        return _from_parts(
            None, match["svc"], match["lvl"], match["msg"],
            trace_kv.group(1) if trace_kv else None,
            ingested_at, user_id=int(match["user"]),
        )

    match = STACK_RE.match(line)
    if match:
        trace_kv = TRACE_KV_RE.search(match["trace_kv"])
        return _from_parts(
            match["ts"], match["svc"], match["lvl"], match["msg"],
            trace_kv.group(1) if trace_kv else None, ingested_at,
        )

    match = SYSLOG_RE.match(line)
    if match:
        trace_kv = TRACE_KV_RE.search(match["trace_kv"]) if match["trace_kv"] else None
        return _from_parts(
            match["ts"], match["svc"], match["lvl"], match["msg"],
            trace_kv.group(1) if trace_kv else None, ingested_at,
        )

    return _from_logfmt(line, ingested_at)


def parse_file(path: Path, ingested_at: datetime | None = None) -> list[dict]:
    """Parsea un archivo completo de logs (JSONL prolijo o log desprolijo)."""
    ingested_at = ingested_at or datetime.now(UTC)
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = parse_line(line, ingested_at)
        if event is not None:
            if event["source_quality"] != "clean" and event["trace_id"] is None:
                event["source_quality"] = "low_confidence"
            events.append(event)
    return events
