"""carga y normalización de archivos → Document"""

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling_core.types.doc import TextItem
from docling_core.types.doc import DoclingDocument
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode
    )

def _pertenece_a_misma_fila(etiqueta: TextItem, valor: TextItem, tolerancia: float = 2.0) -> bool:
    """
    Determina si dos items estan en la misma fila de la pagina usando un margen de tolerancia para la coordenada

    Args:
        etiqueta: El item que representa una etiqueta
        valor: El item con el texto a concatenar a la etiqueta
        tolerancia: La tolerancia para considerar que dos items estan en la misma fila

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

def _get_document_converter() -> DocumentConverter:
    """
    Obtiene una instancia de DocumentConverter configurada para convertir archivos PDF a documentos normalizados.
    Returns:
        DocumentConverter: Instancia configurada de DocumentConverter.
    """
    converter = DocumentConverter(format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options= _generate_pipeline_pdf_options(),
                backend=PyPdfiumDocumentBackend
            )
        })
    
    return converter

def main_nomalice(pdf_file: str) -> DoclingDocument:
    """
    Pipeline para normalizar el contenido de un pdf a un formato para que pueda ser cargado en un motor de busqueda vectorial.

    Args:
        pdf_file (str): Ruta al archivo PDF.
    Returns:
        Document: Documento normalizado listo para ser cargado en un motor de búsqueda vectorial.
    """
    
    converter = _get_document_converter()

    result = converter.convert(pdf_file)

    doc = result.document

    _docling_arreglar_seccion_contrato_de_obra(doc)

    return doc