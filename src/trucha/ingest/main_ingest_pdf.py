"""Pipeline de carga de PDFs a BD de Vectorial e indexación."""
from email.mime import text
from pathlib import Path
import pypdf
from trucha.core.settings import settings
from trucha.ingest.normalice_pdf_vector_search import main_nomalice_vector_search

def validate_hash(file_path: str) -> bool:
    """
    Valida el hash de un archivo PDF para asegurar su integridad. Si es distinto, se considera el archivo como modificado para su reindexación.

    Args:
        file_path (str): Ruta del archivo PDF a validar.
    
    Returns:
        bool: True si el hash coincide, False si no coincide.
    """
    pass

def read_pdf(file_path: str) -> str:
    """
    Lee el contenido de un archivo PDF y devuelve el texto extraído.

    Args:
        file_path (str): Ruta del archivo PDF a leer.

    Returns:
        str: Texto extraído del PDF.
    """
    try:
        with open(file_path, "rb") as f:
            pdf = pypdf.PdfReader(f)

            # Metadatos
            num_paginas = len(pdf.pages)

            contenido_texto = []
            for page_num in range(num_paginas):
                contenido_texto.append("Pagina nro: " + str(page_num + 1 ) + "\n")
                texto = pdf.pages[page_num].extract_text()

                contenido_texto.append(texto.strip())

            text = "\n".join(contenido_texto)

        return text
    except Exception as e:
        return f"Error al leer el PDF: {e}"

def main_ingest_pdf_pipeline():
    # Obtenemos los PDFs en al ruta dentro del proyecto
    project_root = Path(__file__).resolve().parents[3]
    pdf_directory = project_root / Path(settings.pdf_path)
    pdf_files = list(pdf_directory.glob("*.pdf"))
    
    # Ejecutamos el pipeline de ingestión para cada PDF
    for pdf_file in pdf_files:
        main_nomalice_vector_search(pdf_file, root_path=pdf_directory)

if __name__ == "__main__":
    main_ingest_pdf_pipeline()