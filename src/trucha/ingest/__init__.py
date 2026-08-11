"""Ingesta: descubre, trocea y normaliza el contenido del repo."""
from trucha.ingest.scanner import SourceChunk, chunk_text, iter_source_files

__all__ = ["SourceChunk", "chunk_text", "iter_source_files"]
