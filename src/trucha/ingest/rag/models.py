"""Contratos entre etapas"""
from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: str
    text: str
    text_to_embed: str
    meta: dict

@dataclass
class EmbeddedChunk(Chunk):
    embedding: list[float] = field(default_factory=list)
    embed_model: str = ""
