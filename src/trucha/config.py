"""Configuración central de Project Trucha."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRUCHA_", env_file=".env", extra="ignore"
    )

    app_name: str = "project-trucha"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://trucha:trucha@localhost:5432/trucha"
    allowed_roots: Annotated[list[Path], NoDecode] = Field(default_factory=lambda: [Path.cwd()])
    embedding_dimensions: int = 64
    chunk_size_lines: int = 80
    chunk_overlap_lines: int = 10
    max_file_bytes: int = 1_000_000
    search_candidate_limit: int = 40

    @field_validator("allowed_roots", mode="before")
    @classmethod
    def parse_allowed_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return [Path(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_roots")
    @classmethod
    def resolve_allowed_roots(cls, value: list[Path]) -> list[Path]:
        return [path.expanduser().resolve() for path in value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
