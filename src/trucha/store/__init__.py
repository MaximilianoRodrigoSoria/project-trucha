"""Persistencia PostgreSQL y pgvector."""

from trucha.store.database import Base, SessionFactory, engine

__all__ = ["Base", "SessionFactory", "engine"]
