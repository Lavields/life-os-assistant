#!/usr/bin/env python3
"""
Motor de Creación de Presentaciones (PowerPoint, Google Slides y Canva) para asistente
- Genera diapositivas en formato nativo PowerPoint (.pptx) con diseño limpio y estructurado.
- Convierte automáticamente a PDF usando Microsoft PowerPoint en macOS.
- Prepara esquemas compatibles para importar a Google Slides o Canva.
"""

import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.document_engine import convert_pptx_to_pdf
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME, CAREER, INSTITUTION
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME, CAREER, INSTITUTION

OUTPUT_DIR = os.path.join(BASE_DIR, "universidad", "presentaciones")

def create_powerpoint_deck(topic: str, slides_data: list, filename_slug: str = "presentacion") -> dict:
    """
    Crea una presentación formal de PowerPoint y la convierte a PDF.
    slides_data es una lista de dicts:
    [
        {"title": "...", "points": ["...", "..."], "notes": "..."},
        ...
    ]
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    prs = Presentation()
    # 16:9 widescreen layout
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Portada
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]

    title.text = topic
    title.text_frame.paragraphs[0].font.size = Pt(40)
    title.text_frame.paragraphs[0].font.bold = True
    title.text_frame.paragraphs[0].font.color.rgb = RGBColor(20, 35, 60)

    subtitle.text = f"{CAREER} - {INSTITUTION}\nAutor: {USER_NAME} | Asistido por {ASSISTANT_NAME}"
    subtitle.text_frame.paragraphs[0].font.size = Pt(18)
    subtitle.text_frame.paragraphs[0].font.color.rgb = RGBColor(90, 100, 120)

    # Diapositivas de contenido
    blank_layout = prs.slide_layouts[1]
    for s_info in slides_data:
        s = prs.slides.add_slide(blank_layout)
        stitle = s.shapes.title
        stitle.text = s_info.get("title", "")
        stitle.text_frame.paragraphs[0].font.size = Pt(32)
        stitle.text_frame.paragraphs[0].font.bold = True
        stitle.text_frame.paragraphs[0].font.color.rgb = RGBColor(25, 45, 80)

        body = s.placeholders[1]
        tf = body.text_frame
        tf.word_wrap = True
        points = s_info.get("points", [])
        for idx, pt in enumerate(points):
            p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
            p.text = pt
            p.font.size = Pt(20)
            p.font.color.rgb = RGBColor(40, 45, 55)
            p.space_after = Pt(14)

    pptx_path = os.path.join(OUTPUT_DIR, f"{filename_slug}.pptx")
    prs.save(pptx_path)

    # Convertir a PDF con PowerPoint nativo
    pdf_path = os.path.join(OUTPUT_DIR, f"{filename_slug}.pdf")
    try:
        convert_pptx_to_pdf(pptx_path, pdf_path)
    except Exception as e:
        print(f"[PPTX TO PDF ERROR] {e}")
        pdf_path = None

    return {
        "pptx_path": pptx_path,
        "pdf_path": pdf_path,
        "total_slides": len(slides_data) + 1
    }

if __name__ == "__main__":
    test_slides = [
        {
            "title": "Optimización de Procesos Productivos",
            "points": [
                "Diagnóstico de cuellos de botella y tiempos de ciclo.",
                "Balance de línea aplicando teoría de restricciones.",
                "Indicadores de eficiencia global de equipos (OEE)."
            ]
        },
        {
            "title": "Plan de Implementación y Control",
            "points": [
                "Estandarización de operaciones clave.",
                "Monitoreo estadístico de procesos (SPC).",
                "Matriz de asignación de recursos y tiempos."
            ]
        }
    ]
    res = create_powerpoint_deck("Gestión de Operaciones Industriales", test_slides, "test_operaciones")
    print("Presentación creada:")
    print("PPTX:", res["pptx_path"])
    print("PDF:", res["pdf_path"])
