""""""
from typing import Iterator

from trucha.ingest.rag.models import Chunk

from docling_core.types.doc import DoclingDocument
from docling.chunking import HybridChunker

import hashlib

def _preparar_metadata_para_chunk(chunk, cfg_config) -> dict:
    """
     Genera la metadata util para cada chunk
     Args:
        chunk: Un objeto de tipo Chunk que contiene información sobre un fragmento de texto.
        cfg_config: Configuración para la metadata del chunk.
    Returns:
        dict: Un diccionario que contiene la metadata del chunk
    """

    metadata = chunk.meta
    pages = sorted({page.page_no for item in metadata.doc_items for page in (item.prov or [])})

    return {
        "doc_hash": str(metadata.origin.binary_hash) if metadata.origin else "",
        "source":     metadata.origin.filename if metadata.origin else "",
        "headings":   " > ".join(metadata.headings or []),
        "page_start": pages[0] if pages else -1,
        "page_end":   pages[-1] if pages else -1,
        "embed_model": cfg_config.get("EMBED_MODEL"),
    }

def chunk_document(doc: DoclingDocument, tokenizer=None, cfg_config=None) -> Iterator[Chunk]:
    """
    Divide un documento en fragmentos (chunks) basados en el contenido del documento.

    Args:
        doc (DoclingDocument): Documento a dividir en fragmentos.
        tokenizer (Tokenizer, optional): Tokenizer para dividir el texto en tokens.
        cfg_config (dict, optional): Configuración para la metadata del chunk.

    Returns:
        list: Lista de fragmentos del documento.
    """
    chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)

    for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        texto_a_embeber = chunker.contextualize(chunk)
        id = hashlib.sha256(f"{doc.origin.binary_hash}:{i}:{texto_a_embeber}".encode()).hexdigest()

        yield Chunk(
            id=id,
            text= chunk.text,
            text_to_embed=texto_a_embeber,
            meta = _preparar_metadata_para_chunk(chunk, cfg_config=cfg_config),
        )
