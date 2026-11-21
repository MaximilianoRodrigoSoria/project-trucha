"""Normaliza el contenido de un PDF en un formato para que sea indexable en un motor de búsqueda vectorial."""
import logging
import re

from pathlib import Path

from trucha.config.settings import settings

import pypdf
# Librerias de docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling_core.types.doc import TextItem
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode
    )

logger = logging.getLogger(__name__)

# Librerias de splitting
# from langchain.text_splitter import MarkdownHeaderTextSplitter

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

def _pertenece_a_misma_fila(etiqueta: TextItem, valor: TextItem, tolerancia: float = 2.0) -> bool:
    """
    Determina si dos items estan en la misma fila de la pagina usando un margen de tolerancia para la coordenada

    Args:
        etiqueta: El item que representa una etiqueta
        valor: El item con el texto a concatenar a la etiqueta
        tol: La tolerancia para considerar que dos items estan en la misma fila

    Returns:
        bool: True si los items estan en la misma fila, False de lo contrario
    """
    return abs(etiqueta.prov[0].bbox.t - valor.prov[0].bbox.t) < tolerancia

def _docling_arreglar_seccion_contrato_de_obra(doc: DocumentConverter) -> None:
    """
    Arregla el contenido del texto que se encuentra en la sección 'CONTRATO DE OBRA' de un PDF, asegurando que la información esté correctamente formateada y sea coherente.

    Args:
        doc (DocumentConverter): Documento convertido con Docling.
    
    Returns:
        None: Modifica el documento en su lugar.
    """

    # Tomo todos los items
    items = [it for it, _ in doc.iterate_items()
            if isinstance(it, TextItem) and it.prov]

    # Ordenamos los items de mayor a menos que seria del mas arriba a mas abajo en la pagina
    items.sort(key=lambda x: -x.prov[0].bbox.t)

    # Con esto separamos lo que seria las etiquetas de los valores
    etiquetas = [i for i in items if i.text.endswith(":")]
    valores = [i for i in items if not i.text.endswith(":")]

    # guardamos los valores que fueron usados en esta lista para luego eliminarlos del documento.
    valores_usados = []
    for etiqueta in etiquetas:
        valor = next((v for v in valores if v not in valores_usados and _pertenece_a_misma_fila(etiqueta, v)), None)
        if valor is None:
            continue  # etiqueta sin valor: la deja como está
        etiqueta.text = f"- {etiqueta.text} {valor.text}"
        valores_usados.append(valor)

    # Borramos los items que ya fueron usados para concatenar a las etiquetas
    doc.delete_items(node_items=valores_usados)

def procesar_documento(pdf_path: str) -> str:
    """
    Procesa un documento PDF y lo convierte a formato Markdown.

    Args:
        pdf_path (str): Ruta al archivo PDF.

    Returns:
        str: Contenido del PDF en formato Markdown.
    """
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options= _generate_pipeline_pdf_options(),
            backend=PyPdfiumDocumentBackend
        )
    })
    
    result = converter.convert(pdf_path)
    doc = result.document

    _docling_arreglar_seccion_contrato_de_obra(doc)

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
    md_path = Path(f"{root_path}/{settings.md_path}/{pdf_path.stem}.md")

    logger.info(f"Guardando archivo markdown en: {md_path}")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    
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