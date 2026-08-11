from __future__ import annotations

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
from trucha.retrieve import reciprocal_rank_fusion
from trucha.store.models import ChunkModel, FileModel, IndexRunModel, RepositoryModel


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
