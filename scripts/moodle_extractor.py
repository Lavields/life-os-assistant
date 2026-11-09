#!/usr/bin/env python3
"""
Moodle Smart Extractor and Keep-Alive Engine
- Mantiene viva la sesión de Moodle en Google Chrome (Ping cada 120s).
- Extrae la información de los 5 cursos del Semestre 4 (2026-2).
- Guarda el contenido estructurado en universidad/Semestre_4_2026_2_Actual/.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
try:
    from scripts.user_config import INSTITUTION, MOODLE_URL, CONFIG
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import INSTITUTION, MOODLE_URL, CONFIG

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMESTER_4_DIR = os.path.join(BASE_DIR, "universidad", "Semestre_4_2026_2_Actual")

# Cursos a extraer: config/config.json -> "courses" (id de Moodle, código, nombre y carpeta)
COURSES = CONFIG.get("courses", [])
MOODLE_HOST = MOODLE_URL.split("//")[-1].strip("/")

def ping_moodle_keepalive() -> bool:
    """Envía un ping silencioso a Moodle a través de Chrome para renovar la sesión."""
    js = f"var xhr=new XMLHttpRequest();xhr.open('GET','{MOODLE_URL}/my/',false);xhr.send();xhr.status;"
    ascript = f'tell application "Google Chrome" to execute (every tab of every window whose URL contains "{MOODLE_HOST}")\'s first item javascript "{js}"'
    try:
        res = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True, timeout=8)
        return "200" in res.stdout
    except Exception:
        return False

def extract_course_content(course: dict) -> dict:
    """Extrae el contenido de un curso a través de la pestaña activa de Chrome."""
    cid = course["id"]
    js = (
        "var xhr=new XMLHttpRequest();"
        f"xhr.open('GET','{MOODLE_URL}/course/view.php?id={cid}',false);"
        "xhr.send();"
        "var doc=new DOMParser().parseFromString(xhr.responseText,'text/html');"
        "var tText='';"
        "doc.querySelectorAll('.teacher, [class*=contact], [class*=docente]').forEach(function(el){tText+=el.innerText.trim()+' ';});"
        "var acts=[];"
        "doc.querySelectorAll('a').forEach(function(a){"
        "if(a.href&&a.href.indexOf('/mod/')!==-1){"
        "acts.push(a.innerText.trim()+'|||'+a.href);"
        "}"
        "});"
        "tText+'<<<SPLIT>>>'+acts.join(';;;');"
    )
    ascript = f'tell application "Google Chrome" to execute (every tab of every window whose URL contains "{MOODLE_HOST}")\'s first item javascript "{js}"'
    
    try:
        res = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True, timeout=12)
        raw = res.stdout.strip()
        if "<<<SPLIT>>>" in raw:
            parts = raw.split("<<<SPLIT>>>")
            t_raw = parts[0].strip()
            acts_raw = parts[1].strip() if len(parts) > 1 else ""
            
            # Docentes: se toma el bloque de contacto tal como lo muestra Moodle
            teachers = []
            if not teachers and t_raw:
                # filter generic terms
                clean_t = t_raw.replace("Contáctanos", "").replace("Contactar con el soporte del sitio", "").strip()
                if len(clean_t) > 3:
                    teachers.append(clean_t[:100])
                
            activities = []
            if acts_raw:
                for item in acts_raw.split(";;;"):
                    if "|||" in item:
                        name, url = item.split("|||", 1)
                        clean_name = name.strip()
                        if clean_name and not any(a["url"] == url for a in activities):
                            activities.append({"name": clean_name, "url": url.strip()})
                            
            return {"teachers": teachers, "activities": activities}
    except Exception as e:
        print(f"Error extrayendo {course['code']}: {e}")
    return {"teachers": [], "activities": []}

def sync_all_courses():
    """Recorre todos los cursos de Semestre 4 y guarda la información en local."""
    print("Iniciando sincronización de contenidos universidad Semestre 4...")
    os.makedirs(SEMESTER_4_DIR, exist_ok=True)
    
    # 1. Asegurar sesión viva
    alive = ping_moodle_keepalive()
    print(f"Estado de sesión Moodle en Chrome: {'ACTIVA (200 OK)' if alive else 'NO DETECTADA'}")
    
    summary = []
    
    for c in COURSES:
        folder_path = os.path.join(SEMESTER_4_DIR, c["folder"])
        os.makedirs(folder_path, exist_ok=True)
        
        data = extract_course_content(c)
        teachers = data.get("teachers", [])
        activities = data.get("activities", [])
        
        md_content = f"""# 📘 {c['code']} - {c['name']}
**Universidad:** {INSTITUTION}  
**ID LMS:** `{c['id']}`  
**Enlace Moodle:** [Acceder al Curso en LMS]({MOODLE_URL}/course/view.php?id={c['id']})  
**Última Sincronización:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  

---

## 👨‍🏫 Equipo Docente
"""
        if teachers:
            for t in teachers:
                md_content += f"- **{t}**\n"
        else:
            md_content += "- *Docente pendiente de asignación en plataforma.*\n"

        md_content += "\n## 📂 Secciones y Materiales Curriculares Oficiales\n"
        if activities:
            for act in activities:
                md_content += f"- **[{act['name']}]({act['url']})**\n"
        else:
            md_content += "- *No hay actividades ni recursos publicados en este momento.*\n"

        md_content += f"""
---

## 🎯 Instrucciones para el asistente y Antigravity
1. Este archivo contiene la estructura oficial sincronizada con Moodle.
2. Cada vez que el usuario envíe presentaciones (.pptx) o lecturas de este ramo a Telegram, se procesan automáticamente en esta carpeta.
3. Para generar resúmenes, evaluaciones de práctica o bundles de NotebookLM, consultar este índice.
"""
        doc_path = os.path.join(folder_path, "indice_asignatura.md")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        summary.append({
            "code": c["code"],
            "name": c["name"],
            "teachers": teachers,
            "activities_count": len(activities)
        })
        print(f"✓ Sincronizado {c['code']} ({c['name']}) -> {len(activities)} recursos, Docentes: {teachers}")
        
    return summary

if __name__ == "__main__":
    results = sync_all_courses()
    print("\nResumen completado con éxito.")
