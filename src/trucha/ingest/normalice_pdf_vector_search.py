"""Normaliza el contenido de un PDF en un formato para que sea indexable en un motor de búsqueda vectorial."""
from pathlib import Path
from trucha.core.settings import settings

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode
    )

def embeding_text(chunks: list[str]) -> list[list[float]]:
    pass

def chunk_text(texto: str, chunk_size: int = 500) -> list[str]:
    pass

def _generate_pipeline_pdf_options() -> PdfPipelineOptions:
    """
    Genera las opciones de pipeline para el procesamiento de PDFs.
    """
    return PdfPipelineOptions(
        enable_remote_services=False,
        do_ocr=False,
        do_table_structure=True,
        generate_picture_images=False,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE
        )
    )

def procesar_documento(pdf_path: str) -> str:
    """
    Procesa un documento PDF y lo convierte a formato Markdown.

    Args:
        pdf_path (str): Ruta al archivo PDF.

    Returns:
        str: Contenido del PDF en formato Markdown.
    """
    converter = DocumentConverter(format_option={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options= _generate_pipeline_pdf_options(),
            backend=PyPdfiumDocumentBackend()
        )
    })
    
    result = converter.convert(pdf_path)
    doc = result.document

    content = doc.export_to_markdown(
        page_break_placeholder="---PAGE BREAK---",
        include_annotations=True,
        mark_annotations=True
    )

    return content

def _pipeline_generar_archivo_markdown(pdf_path: Path, root_path: Path = None) -> str:
    """
    1° paso para la normalizacion del texto. Reordena el contenido de un PDF en un formato Markdown

    Args:
        pdf_path (str): Ruta al archivo PDF.

    Returns:
        str: Contenido del PDF reordenado en formato Markdown.
    """
    texto_md = procesar_documento(pdf_path)
    # guardamos el archivo en markdown manteniendo el mismo nombre del pdf pero con extension .md
    md_path = Path(f"{root_path}/{settings.md_path}/{pdf_path.name().replace('.pdf', '')}.md")

    md_path.write_text(texto_md, encoding="utf-8")

    return texto_md
    

def main_nomalice_vector_search(pdf_path: Path, root_path: Path = None):
    """
    Pipeline para normalizar el contenido de un pdf a un formato para que pueda ser cargado en un motor de busqueda vectorial.

    Args:
        pdf_path (str): Ruta al archivo PDF.
    Returns:
        list[list[float]]: Embeddings del contenido del PDF.
    """
    texto_md = _pipeline_generar_archivo_markdown(pdf_path, root_path)

    chunks = chunk_text(texto_md, chunk_size=500)

    embeddings = embeding_text(chunks)

    return embeddings