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

def _read_pdf_with_pypdf(file_path: str) -> str:
    """
    Lee el contenido de un archivo PDF y devuelve el texto extraído.
    Leemos con Pypdf porque con docling se genera un problema con la separacion entre texto que lo concidera como dos bloques de texto y son dos parrafos disntintos, cosa que no ocurre con PyPDF.

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

            text = " ".join(contenido_texto)

        logger.info(f"Se leyó el PDF: {file_path} con éxito. Número de páginas: {num_paginas}")
        return text
    except Exception as e:
        logger.error(f"Error al leer el PDF: {e}")
        return f"Error al leer el PDF: {e}"

def _eliminar_saltos_de_linea(texto: str) -> str:
    """
    Elimina los saltos de línea innecesarios en un texto que se genera en la seccion 'CONTRATO DE OBRA', manteniendo la coherencia del contenido.
    Args:
        texto (str): Texto original con posibles saltos de línea.
    Returns:
        str: Texto sin saltos de línea innecesarios.
    """
    patron = r"(?ms)(^Obra:(.*?)^Fecha de firma:\n(.*?)\n)"
    
    resultado = re.search(patron, texto)
    substring = resultado.group(1).strip()

    # Reeplazamos los saltos de linea que se encuentra dentro del substring del patron
    substring_modficado = substring.replace(":\n", ": ")

    return substring_modficado

def _arreglar_seccion_contrato_de_obra(texto_docling: str, pdf_path: str) -> str:
    """
    Arregla el contenido del texto que se encuentra en la sección 'CONTRATO DE OBRA' de un PDF, asegurando que la información esté correctamente formateada y sea coherente.

    Args:
        texto_docling (str): Texto original extraído del PDF con Docling.
        pdf_path (str): Ruta al archivo PDF.
    Returns:
        str: Texto con la sección 'CONTRATO DE OBRA' arreglada.
    """
    # PREPARACION DE LA CORRECCION
    texto_pypdf = _read_pdf_with_pypdf(pdf_path)    
    texto_pypdf_modficiado = _eliminar_saltos_de_linea(texto_pypdf)

    # REALIZANDO CORRECCION
    # Seleccion del error
    patron_texto_docling = r"(?ms)(^Obra:(.*?))^## Cláusula Primera – Objeto"
    resultado_docling = re.search(patron_texto_docling, texto_docling)
    texto_erroneo_docling = resultado_docling.group(1).strip()
    texto_docling_corregido = texto_docling.replace(texto_erroneo_docling, texto_pypdf_modficiado)

    return texto_docling_corregido.strip()

def postprocesado_texto(texto: str, pdf_path: str) -> str:
    """
    Realiza un postprocesado del texto extraído de un PDF para mejorar su legibilidad y coherencia.

    Args:
        texto (str): Texto extraído del PDF.

    Returns:
        str: Texto postprocesado.
    """
    texto = _arreglar_seccion_contrato_de_obra(texto, pdf_path)

    return texto

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

    content = doc.export_to_markdown(
        page_break_placeholder="---PAGE BREAK---",
        include_annotations=True,
        mark_annotations=True
    )

    content = postprocesado_texto(content, pdf_path)

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