"""Pipeline de carga de PDFs a BD de Vectorial e indexación."""

import logging
from pathlib import Path

from trucha.config.settings import settings
from trucha.ingest.normalice_pdf_vector_search import main_nomalice_vector_search

logger = logging.getLogger(__name__)

def validate_hash(file_path: str) -> bool:
    """
    Valida el hash de un archivo PDF para asegurar su integridad. Si es distinto, se considera el archivo como modificado para su reindexación.

    Args:
        file_path (str): Ruta del archivo PDF a validar.
    
    Returns:
        bool: True si el hash coincide, False si no coincide.
    """
    pass

def main_ingest_pdf_pipeline():
    # Obtenemos los PDFs en al ruta dentro del proyecto
    project_root = Path(__file__).resolve().parents[3]

    logger.debug(f"Ruta del proyecto: {project_root}")
    logger.debug(f"Ruta de PDFs: {Path(settings.pdf_path)}")

    pdf_directory = project_root / Path(settings.pdf_path)
    pdf_files = list(pdf_directory.glob("*.pdf"))

    logger.info(f"Se encontraron {len(pdf_files)} archivos PDF en la ruta: {pdf_directory}")
    # Ejecutamos el pipeline de ingestión para cada PDF
    for pdf_file in pdf_files:
        main_nomalice_vector_search(pdf_file, root_path=project_root)

if __name__ == "__main__":
    logger.info("Iniciando pipeline de ingestión de PDFs...")
    main_ingest_pdf_pipeline()