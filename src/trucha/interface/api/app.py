from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trucha.config import get_settings
from trucha.interface.api.schemas import (
    DecisionCreate,
    DecisionRead,
    IndexRunRead,
    RepositoryCreate,
    RepositoryRead,
    SearchRequest,
    SearchResult,
)
from trucha.services import create_repository, hybrid_search, index_repository
from trucha.store.database import close_engine, get_session
from trucha.store.models import DecisionModel, IndexRunModel


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @api.get("/health", tags=["system"])
    async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @api.post("/api/v1/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
    async def register_repository(payload: RepositoryCreate, session: AsyncSession = Depends(get_session)):
        try:
            return await create_repository(session, payload.name, payload.root, settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Ya existe un repositorio con ese nombre") from exc

    @api.post("/api/v1/repositories/{repository_id}/index", response_model=IndexRunRead)
    async def run_index(repository_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
        try:
            return await index_repository(session, repository_id, settings)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.get("/api/v1/index-runs/{run_id}", response_model=IndexRunRead)
    async def get_index_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
        run = await session.get(IndexRunModel, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        return run

    @api.post("/api/v1/search", response_model=list[SearchResult])
    async def search(payload: SearchRequest, session: AsyncSession = Depends(get_session)):
        return await hybrid_search(session, payload.query, payload.repository_id, payload.limit, settings)

    @api.post("/api/v1/decisions", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
    async def create_decision(payload: DecisionCreate, session: AsyncSession = Depends(get_session)):
        decision = DecisionModel(**payload.model_dump())
        session.add(decision)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=404, detail="Repositorio no encontrado") from exc
        await session.refresh(decision)
        return decision

    @api.get("/api/v1/decisions", response_model=list[DecisionRead])
    async def list_decisions(
        repository_id: uuid.UUID | None = Query(default=None),
        session: AsyncSession = Depends(get_session),
    ):
        statement = select(DecisionModel).order_by(DecisionModel.created_at.desc())
        if repository_id:
            statement = statement.where(DecisionModel.repository_id == repository_id)
        return list((await session.scalars(statement)).all())

    return api


app = create_app()
