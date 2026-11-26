"""list[Chunk] → chunks con vector"""

import logging

from typing import Iterator
from trucha.ingest.rag.models import Chunk, EmbeddedChunk

from transformers import AutoTokenizer

from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)

def get_tokenizer(cfg_config: dict = None):
    """
    Obtiene un tokenizer basado en la configuración proporcionada.

    Args:
        cfg_config (dict, optional): Configuración para el tokenizer. Si no se proporciona, se utilizará la configuración predeterminada.

    Returns:
        Tokenizer: Instancia del tokenizer.
    """

    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(cfg_config.get("EMBED_MODEL")),
        max_tokens=cfg_config.get("MAX_TOKENS", 512)  # Valor predeterminado de 512 si no se proporciona
    )
    return tokenizer

def get_embed_model(cfg_config: dict = None):
    """
    Obtiene un modelo de embedding basado en la configuración proporcionada.

    Args:
        cfg_config (dict, optional): Configuración para el modelo de embedding. Si no se proporciona, se utilizará la configuración predeterminada.

    Returns:
        SentenceTransformer: Instancia del modelo de embedding.
    """
    model = SentenceTransformer(cfg_config.get("EMBED_MODEL"))
    return model

def embed_chunks(chunks: Iterator[Chunk], model: SentenceTransformer, cfg_config: dict = None) -> Iterator[EmbeddedChunk]:
    """
    Embebe una lista de chunks utilizando el modelo de embedding proporcionado.

    Args:
        chunks (Iterator[Chunk]): Lista de chunks a embeder.
        model (SentenceTransformer): Modelo de embedding a utilizar.
        cfg_config (dict, optional): Configuración adicional para el embedding.
    Returns:
        Iterator[EmbeddedChunk]: Lista de chunks embebidos.
    """
    batch = []
    for chunk in chunks:
        batch.append(chunk)
        if len(batch) == cfg_config.get("BATCH_SIZE", 64):
            yield from _embed_batch(batch, model, cfg_config.get("EMBED_MODEL"))
            batch = []
    if batch:
        yield from _embed_batch(batch, model, cfg_config.get("EMBED_MODEL"))

def _embed_batch(batch, model, model_id):
    vecs = model.encode([c.text_to_embed for c in batch])
    for c, v in zip(batch, vecs):
        yield EmbeddedChunk(**vars(c), embedding=v.tolist(), embed_model=model_id)
