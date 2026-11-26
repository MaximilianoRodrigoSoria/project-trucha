"""orquestador"""
import logging
from pathlib import Path

from trucha.config.settings import settings

# librerias de pipeline
from trucha.ingest.rag.embedding import get_tokenizer, get_embed_model, embed_chunks
from trucha.ingest.rag.normalice import main_nomalice
from trucha.ingest.rag.chunking import chunk_document

# Configuración del logger
logging.basicConfig(
    level= getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
 
logger = logging.getLogger(__name__)

def run(pdf_directory: Path = None):
    """
    Función principal que orquesta la ejecución del pipeline de ingestión de PDFs.

    args:
        pdf_directory (Path, optional): Directorio donde se encuentran los archivos PDF.
    """
    pdf_files = list(pdf_directory.glob("*.pdf"))
    
    logger.info(f"Se encontraron {len(pdf_files)} archivos PDF en la ruta: {pdf_directory}")

    tokenizer = get_tokenizer(settings.model_dump())  # Inicializa el tokenizer una vez antes del bucle
    model = get_embed_model(settings.model_dump())  # Inicializa el modelo de embedding una vez antes del bucle

    for pdf_file in pdf_files:
        doc = main_nomalice(pdf_file)

        chunks = chunk_document(doc, tokenizer=tokenizer, cfg_config=settings.model_dump())

        embedded_chunks = embed_chunks(chunks, model=model, cfg_config=settings.model_dump())
        for emb_chunk in embedded_chunks:
            logger.debug(f"Chunk ID: {emb_chunk.id}, Text: {emb_chunk.text[:50]}..., text_to_embed: {emb_chunk.text_to_embed[:150]}..., meta: {emb_chunk.meta}, Embedding: {emb_chunk.embedding[:10]}")  # Muestra los primeros 50 caracteres del texto del chunk
        

if __name__ == "__main__":
    logger.info("Iniciando orquestador de ingestión de PDFs...")
    # Obtenemos los PDFs en al ruta dentro del proyecto
    project_root = Path(__file__).resolve().parents[4]

    logger.debug(f"Ruta del proyecto: {project_root}")
    logger.debug(f"Ruta de PDFs: {Path(settings.pdf_path)}")

    pdf_directory = project_root / Path(settings.pdf_path)
    run(pdf_directory=pdf_directory)