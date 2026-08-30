from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trucha.config import Settings
from trucha.embed import embed_text
from trucha.ingest.scanner import (
    chunk_text,
    detect_language,
    iter_source_files,
    read_text,
    sha256_text,
    validate_repository_path,
)
from trucha.logs.trace import traces_from_events
from trucha.retrieve import reciprocal_rank_fusion
from trucha.store.models import (
    ChunkModel,
    FileModel,
    IndexRunModel,
    RepositoryModel,
    TraceModel,
)

_STATUS_CODE_RE = re.compile(r"\bresponse (\d{3})\b")


async def create_repository(
    session: AsyncSession, name: str, root: str, settings: Settings
) -> RepositoryModel:
    resolved = validate_repository_path(Path(root), settings.allowed_roots)
    repository = RepositoryModel(name=name, root=str(resolved))
    session.add(repository)
    await session.commit()
    await session.refresh(repository)
    return repository


async def index_repository(
    session: AsyncSession, repository_id: uuid.UUID, settings: Settings
) -> IndexRunModel:
    repository = await session.get(RepositoryModel, repository_id)
    if repository is None:
        raise LookupError("Repositorio no encontrado")

    root = validate_repository_path(Path(repository.root), settings.allowed_roots)
    run = IndexRunModel(repository_id=repository.id, status="running", stats={})
    session.add(run)
    await session.commit()
    stats = {"scanned": 0, "indexed": 0, "unchanged": 0, "removed": 0, "chunks": 0}

    try:
        existing = {
            item.relative_path: item
            for item in (await session.scalars(select(FileModel).where(FileModel.repository_id == repository.id))).all()
        }
        seen: set[str] = set()
        for path in iter_source_files(root, settings.max_file_bytes):
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            stats["scanned"] += 1
            content = read_text(path)
            if content is None:
                continue
            digest = sha256_text(content)
            stored = existing.get(relative)
            if stored and stored.content_hash == digest:
                stats["unchanged"] += 1
                continue
            if stored:
                await session.delete(stored)
                await session.flush()
            file_model = FileModel(
                repository_id=repository.id,
                relative_path=relative,
                content_hash=digest,
                language=detect_language(path),
                size_bytes=path.stat().st_size,
            )
            session.add(file_model)
            await session.flush()
            for chunk in chunk_text(content, settings.chunk_size_lines, settings.chunk_overlap_lines):
                session.add(ChunkModel(
                    file_id=file_model.id,
                    ordinal=chunk.ordinal,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    text=chunk.text,
                    embedding=embed_text(chunk.text, settings.embedding_dimensions),
                ))
                stats["chunks"] += 1
            stats["indexed"] += 1

        for relative, stored in existing.items():
            if relative not in seen:
                await session.delete(stored)
                stats["removed"] += 1

        run.status = "completed"
        run.stats = stats
        run.finished_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
        return run
    except Exception as exc:
        await session.rollback()
        run = await session.get(IndexRunModel, run.id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            run.stats = stats
            run.finished_at = datetime.now(UTC)
            await session.commit()
        raise


async def hybrid_search(
    session: AsyncSession,
    query: str,
    repository_id: uuid.UUID | None,
    limit: int,
    settings: Settings,
) -> list[dict[str, object]]:
    candidate_limit = max(limit, settings.search_candidate_limit)
    base_filter = []
    if repository_id:
        base_filter.append(FileModel.repository_id == repository_id)

    ts_query = func.plainto_tsquery("simple", query)
    lexical_score = func.ts_rank_cd(func.to_tsvector("simple", ChunkModel.text), ts_query)
    lexical_stmt = (
        select(ChunkModel, FileModel, lexical_score.label("score"))
        .join(FileModel, ChunkModel.file_id == FileModel.id)
        .where(*base_filter, func.to_tsvector("simple", ChunkModel.text).op("@@")(ts_query))
        .order_by(lexical_score.desc())
        .limit(candidate_limit)
    )
    vector = embed_text(query, settings.embedding_dimensions)
    distance = ChunkModel.embedding.cosine_distance(vector)
    vector_stmt = (
        select(ChunkModel, FileModel, distance.label("distance"))
        .join(FileModel, ChunkModel.file_id == FileModel.id)
        .where(*base_filter)
        .order_by(distance)
        .limit(candidate_limit)
    )
    lexical_rows = (await session.execute(lexical_stmt)).all()
    vector_rows = (await session.execute(vector_stmt)).all()
    lexical_ids = [row[0].id for row in lexical_rows]
    vector_ids = [row[0].id for row in vector_rows]
    fused = reciprocal_rank_fusion([lexical_ids, vector_ids])
    rows = {row[0].id: row for row in lexical_rows + vector_rows}
    lexical_values = {row[0].id: float(row[2]) for row in lexical_rows}
    vector_values = {row[0].id: 1.0 - float(row[2]) for row in vector_rows}
    ordered = sorted(fused, key=fused.get, reverse=True)[:limit]
    return [
        {
            "chunk_id": chunk_id,
            "path": rows[chunk_id][1].relative_path,
            "start_line": rows[chunk_id][0].start_line,
            "end_line": rows[chunk_id][0].end_line,
            "snippet": rows[chunk_id][0].text[:800],
            "lexical_score": lexical_values.get(chunk_id, 0.0),
            "vector_score": vector_values.get(chunk_id, 0.0),
            "hybrid_score": fused[chunk_id],
        }
        for chunk_id in ordered
    ]


def _trace_status_code(trace: dict) -> int | None:
    for event in trace["events"]:
        match = _STATUS_CODE_RE.search(event["message"])
        if match:
            return int(match.group(1))
    return None


def _trace_to_rows(trace: dict, source_path: str, settings: Settings) -> TraceModel:
    services = sorted({event["service"] for event in trace["events"] if event.get("service")})
    levels = sorted({event["level"] for event in trace["events"] if event.get("level")})
    return TraceModel(
        trace_id=trace["trace_id"],
        summary=trace["summary"],
        embedding=embed_text(trace["summary"], settings.embedding_dimensions),
        outcome=trace["outcome"],
        source_quality=trace["source_quality"],
        services=services,
        levels=levels,
        user_id=trace["user_id"],
        payment_id=trace["payment_id"],
        status_code=_trace_status_code(trace),
        source_path=str(source_path),
        event_count=len(trace["events"]),
    )


async def ingest_logs(
    session: AsyncSession,
    source_paths: list[str | Path],
    settings: Settings,
) -> dict[str, int]:
    """Paso 3: parsea archivos de logs y guarda el resumen vectorizado de
    cada traza en pgvector (idempotente por source_path + trace_id).

    Devuelve stats: {'sources': n, 'parsed': n, 'traces': n, 'inserted': n,
    'skipped': n, 'errors': n}.
    """
    stats: dict[str, int] = {
        "sources": 0, "parsed": 0, "traces": 0, "inserted": 0,
        "skipped": 0, "errors": 0,
    }
    for source in source_paths:
        path = Path(source)
        stats["sources"] += 1
        try:
            traces = traces_from_events(_parse_log_file(path))
        except Exception:  # noqa: BLE001 - un archivo corrupto no debe abortar el resto
            stats["errors"] += 1
            continue
        stats["parsed"] += len(traces)
        existing = {
            row.trace_id
            for row in (
                await session.scalars(
                    select(TraceModel.trace_id).where(TraceModel.source_path == str(path))
                )
            ).all()
        }
        for trace in traces:
            stats["traces"] += 1
            if trace["trace_id"] in existing:
                stats["skipped"] += 1
                continue
            session.add(_trace_to_rows(trace, str(path), settings))
        await session.commit()
    return stats


def _parse_log_file(path: Path) -> list[dict]:
    """Parsea un archivo de logs (JSONL prolijo o log desprolijo) a eventos
    unificados, reutilizando la cascada de parsers de trucha.logs.parse."""
    from trucha.logs.parse import parse_file

    return parse_file(path)


async def hybrid_log_search(
    session: AsyncSession,
    graph: object | None,
    query: str,
    settings: Settings,
    limit: int = 10,
    filter_quality: str | None = None,
) -> list[dict[str, object]]:
    """Paso 5: recuperación híbrida sobre trazas vectorizadas.

    1. Búsqueda semántica en pgvector (top-k trazas por proximidad del
       embedding del resumen narrativo a la pregunta).
    2. Con esos trace_ids, entra al grafo causal y trae la cadena
       completa (antes/después, en qué servicio).
    3. Marca las trazas cuyo source_quality no es 'clean' para que la
       capa de respuesta pueda avisar que son inferidas/reparadas.

    `graph` puede ser `None` (sin Neo4j): devuelve las trazas del vector
    store sin expandir la cadena causal.
    """
    candidate_limit = max(limit, settings.search_candidate_limit)
    vector = embed_text(query, settings.embedding_dimensions)
    distance = TraceModel.embedding.cosine_distance(vector)

    statement = (
        select(TraceModel, distance.label("distance"))
        .order_by(distance)
        .limit(candidate_limit)
    )
    if filter_quality:
        statement = statement.where(TraceModel.source_quality == filter_quality)

    rows = (await session.execute(statement)).all()
    ordered = sorted(rows, key=lambda row: float(row[1]))[:limit]
    trace_ids = [row[0].trace_id for row in ordered]

    causal_chains: dict[str, list[dict]] = {}
    if graph is not None and trace_ids:
        for trace_id in trace_ids:
            try:
                causal_chains[trace_id] = await graph.causal_chain(trace_id)
            except Exception:  # noqa: BLE001 - la búsqueda no debe romper por el grafo
                causal_chains[trace_id] = []

    results = []
    for row in ordered:
        trace, _ = row
        trace_id = trace.trace_id
        chain = causal_chains.get(trace_id, [])
        low_confidence = trace.source_quality != "clean"
        results.append({
            "trace_id": trace_id,
            "summary": trace.summary,
            "outcome": trace.outcome,
            "services": trace.services,
            "levels": trace.levels,
            "user_id": trace.user_id,
            "payment_id": trace.payment_id,
            "status_code": trace.status_code,
            "source_quality": trace.source_quality,
            "event_count": trace.event_count,
            "source_path": trace.source_path,
            "vector_score": 1.0 - float(row[1]),
            "low_confidence": low_confidence,
            "causal_chain": chain,
        })
    return results
