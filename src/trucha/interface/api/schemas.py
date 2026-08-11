from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    root: str = Field(min_length=1)


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    root: str
    created_at: datetime


class IndexRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    repository_id: uuid.UUID
    status: str
    stats: dict[str, int]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    repository_id: uuid.UUID | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    path: str
    start_line: int
    end_line: int
    snippet: str
    lexical_score: float
    vector_score: float
    hybrid_score: float


class DecisionCreate(BaseModel):
    repository_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    paths: list[str] = Field(default_factory=list)
    author: str = Field(default="unknown", max_length=200)


class DecisionRead(DecisionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
