#!/usr/bin/env python3
"""
Motor de Procesamiento de Documentos y Cuadernos NotebookLM (asistente)
- Convierte presentaciones (.pptx / .ppt) a PDF nativo de alta resolución usando Microsoft PowerPoint (AppleScript).
- Extrae texto y conceptos clave con python-pptx y pypdf.
- Genera paquetes de estudio optimizados para NotebookLM de Google con prompts analíticos para Ingeniería Industrial.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from pptx import Presentation
from pypdf import PdfReader
try:
    from scripts.user_config import CAREER, INSTITUTION
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import CAREER, INSTITUTION

DEFAULT_STUDY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "universidad", "estudio")

def convert_pptx_to_pdf(pptx_path: str, pdf_path: str = None) -> str:
    """
    Convierte un archivo PPTX a PDF usando Microsoft PowerPoint en macOS.
    """
    pptx_path = os.path.abspath(pptx_path)
    if not os.path.exists(pptx_path):
        raise FileNotFoundError(f"No se encontró el archivo: {pptx_path}")

    if not pdf_path:
        pdf_path = os.path.splitext(pptx_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    script = f'''
set pptxFile to POSIX file "{pptx_path}"
set pdfFile to POSIX file "{pdf_path}"
tell application "Microsoft PowerPoint"
    open pptxFile
    save active presentation in pdfFile as save as PDF
    close active presentation saving no
end tell
'''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Error al convertir PPTX a PDF: {res.stderr}")

    if not os.path.exists(pdf_path):
        raise RuntimeError(f"El archivo PDF no se generó en la ruta esperada: {pdf_path}")

    return pdf_path

def extract_text_from_pptx(pptx_path: str) -> dict:
    """Extrae títulos y textos estructurados por diapositiva."""
    prs = Presentation(pptx_path)
    slides_data = []
    
    for i, slide in enumerate(prs.slides):
        slide_text = []
        slide_title = ""
        if slide.shapes.title and slide.shapes.title.text:
            slide_title = slide.shapes.title.text.strip()

        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    t = paragraph.text.strip()
                    if t and t != slide_title:
                        slide_text.append(t)

        slides_data.append({
            "slide_number": i + 1,
            "title": slide_title,
            "content": slide_text
        })

    return {
        "filename": os.path.basename(pptx_path),
        "total_slides": len(slides_data),
        "slides": slides_data
    }

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrae texto plano de un PDF."""
    reader = PdfReader(pdf_path)
    text_parts = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text()
        if t:
            text_parts.append(f"--- PÁGINA {i+1} ---\n{t.strip()}")
    return "\n\n".join(text_parts)

def build_notebooklm_bundle(input_path: str, destination_dir: str = DEFAULT_STUDY_DIR) -> dict:
    """
    Toma un PPTX o PDF, lo procesa, genera el PDF final y un cuaderno de estudio para NotebookLM.
    """
    os.makedirs(destination_dir, exist_ok=True)
    input_path = os.path.abspath(input_path)
    base_name = Path(input_path).stem

    pdf_target_path = os.path.join(destination_dir, f"{base_name}.pdf")

    if input_path.lower().endswith((".pptx", ".ppt")):
        print(f"[DOC] Convirtiendo {input_path} a PDF...")
        convert_pptx_to_pdf(input_path, pdf_target_path)
        extracted = extract_text_from_pptx(input_path)
        slides_text = []
        for s in extracted["slides"]:
            slides_text.append(f"### Diapositiva {s['slide_number']}: {s['title']}\n" + "\n".join(f"- {c}" for c in s["content"]))
        body_content = "\n\n".join(slides_text)
    else:
        pdf_target_path = input_path
        body_content = extract_text_from_pdf(input_path)

    # Crear Guía y Prompt de NotebookLM
    notebook_md_path = os.path.join(destination_dir, f"{base_name}_NotebookLM_Guia.md")
    
    prompt_notebooklm = f"""Actúa como un Profesor y Tutor Senior de {CAREER} en {INSTITUTION}. 
He cargado las diapositivas oficiales de la materia '{base_name}'.
Tu objetivo es ayudarme a comprender los principios fundamentales, modelos matemáticos, diagramas de procesos y aplicaciones prácticas.
Por favor:
1. Genera un resumen ejecutivo de los 5 conceptos nucleares de este documento.
2. Identifica posibles preguntas de examen o casos prácticos de aplicación en la industria chilena.
3. Si hay fórmulas o metodologías, explica el paso a paso de su cálculo de forma intuitiva y visual.
4. No uses lenguaje innecesariamente denso; prioriza el pensamiento sistémico, la causa-efecto y la eficiencia industrial."""

    content_md = f"""# Cuaderno de Estudio: {base_name}
> **Carrera:** Ingeniería en Ejecución Industrial - universidad  
> **Archivo PDF Fuente:** `{os.path.basename(pdf_target_path)}`  
> **Herramienta Recomendada:** [NotebookLM de Google](https://notebooklm.google.com)

---

## 1. Prompt Especializado para NotebookLM
*Copia y pega este prompt exacto en el chat de NotebookLM tras subir el PDF:*

```text
{prompt_notebooklm}
```

---

## 2. Contenido Estructurado Extraído de las Diapositivas

{body_content}
"""

    with open(notebook_md_path, "w", encoding="utf-8") as f:
        f.write(content_md)

    return {
        "pdf_path": pdf_target_path,
        "notebook_md_path": notebook_md_path,
        "prompt_notebooklm": prompt_notebooklm
    }

if __name__ == "__main__":
    # Prueba rápida
    test_pptx = "/tmp/test_presentation.pptx"
    if os.path.exists(test_pptx):
        result = build_notebooklm_bundle(test_pptx)
        print("Bundle creado con éxito:")
        print("PDF:", result["pdf_path"])
        print("Guía Markdown:", result["notebook_md_path"])
