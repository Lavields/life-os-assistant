#!/usr/bin/env python3
"""
Módulo de Escaneo Unificado Académico y Detección de Tareas
- Escanea correos en Apple Mail:
    * Institucional universidad: el correo institucional (Cuenta 'Exchange', buzón 'Bandeja de entrada')
    * Personal: el correo personal (Cuenta 'Google', buzón 'INBOX')
- Extrae evaluaciones, avisos de tareas y fechas límite de Moodle.
- Desduplica tareas para identificar si un aviso de correo corresponde a una tarea ya registrada.
- Genera y mantiene actualizado el documento central memoria/tareas_pendientes.md y tareas_pendientes.json.
- Sincroniza automáticamente los recordatorios con fecha fatal en el iPhone vía Apple Reminders.
"""

import os
import sys
import re
import json
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
TAREAS_JSON = os.path.join(MEMORIA_DIR, "tareas_pendientes.json")
TAREAS_MD = os.path.join(MEMORIA_DIR, "tareas_pendientes.md")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.apple_reminders import create_apple_reminder, list_apple_reminders

KEYWORDS_ACADEMIC = [
    "tarea", "entrega", "evaluacion", "evaluación", "examen", "certamen",
    "ficha", "informe", "proyecto", "vencimiento", "vence", "fecha límite",
    "lms", "moodle", "ucm", "iej"
]

def scan_exchange_academic(limit: int = 25) -> List[Dict]:
    """
    Escanea mensajes académicos de Exchange (el correo institucional) de forma ultra rápida y robusta.
    """
    script = f'''
tell application "Mail"
    set resText to ""
    try
        set acc to account "Exchange"
        set mb to mailbox "Bandeja de entrada" of acc
        set ucmMsgs to (messages of mb whose sender contains "ucm.cl")
        set tot to count of ucmMsgs
        if tot > {limit} then set tot to {limit}
        repeat with i from 1 to tot
            set m to item i of ucmMsgs
            set s to subject of m
            set snd to sender of m
            set d to (date received of m as text)
            set cont to ""
            if s contains "Tiene tareas" or s contains "entrega" then
                try
                    set cont to content of m
                    if (length of cont) > 500 then set cont to text 1 thru 500 of cont
                end try
            end if
            set resText to resText & s & "|||" & snd & "|||" & d & "|||" & cont & "###MSG###"
        end repeat
    end try
    return resText
end tell
'''
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=25)
        if p.returncode != 0:
            return []
        
        raw_items = p.stdout.strip().split("###MSG###")
        messages = []
        for raw in raw_items:
            parts = raw.split("|||")
            if len(parts) >= 4:
                subj, sndr, dt = parts[0].strip(), parts[1].strip(), parts[2].strip()
                content = parts[3].strip() if len(parts) > 3 else ""
                if subj:
                    messages.append({
                        "account": "el correo institucional",
                        "subject": subj,
                        "sender": sndr,
                        "date": dt,
                        "content": content
                    })
        return messages
    except Exception as e:
        print(f"[SCAN EXCHANGE ERROR] {e}")
        return []

def scan_google_academic(limit: int = 15) -> List[Dict]:
    """
    Escanea los mensajes más recientes de Google (el correo personal).
    """
    script = f'''
tell application "Mail"
    set res to {{}}
    try
        set acc to account "Google"
        set mb to mailbox "INBOX" of acc
        set msgBatch to (messages 1 thru {limit} of mb)
        repeat with m in msgBatch
            set s to subject of m
            set snd to sender of m
            set low to (s & " " & snd)
            if low contains "ucm" or low contains "tarea" or low contains "evalua" or low contains "certamen" then
                set d to (date received of m as text)
                set end of res to ("Google|||" & s & "|||" & snd & "|||" & d & "|||")
            end if
        end repeat
    on error err
        set end of res to ("ERROR|||" & err & "||||||")
    end try
    return res
end tell
'''
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if p.returncode != 0:
            return []
        raw_items = p.stdout.strip().split(", ")
        messages = []
        for raw in raw_items:
            parts = raw.split("|||")
            if len(parts) >= 4:
                acc, subj, sndr, dt = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                if acc != "ERROR":
                    messages.append({
                        "account": "el correo personal",
                        "subject": subj,
                        "sender": sndr,
                        "date": dt,
                        "content": ""
                    })
        return messages
    except Exception as e:
        print(f"[SCAN GOOGLE ERROR] {e}")
        return []

def clean_course_name(name: str) -> str:
    """Limpia códigos de curso, secciones y mayúsculas excesivas."""
    if not name:
        return "Universidad"
    # Eliminar -S1, -S2, etc.
    name = re.sub(r'-S\d+', '', name)
    # Eliminar [IEJ223], [IEJ], etc.
    name = re.sub(r'\[.*?\]', '', name)
    # Eliminar (SAN MIGUEL...) u otros paréntesis
    name = re.sub(r'\(.*?\)', '', name)
    name = name.strip()
    if not name or name.lower() in ["ucm pregrado", "pregrado", "ucm"]:
        return "Universidad"
    # Capitalizar palabras en formato Título limpio
    words = name.split()
    clean_words = []
    for w in words:
        if w.upper() in ["I", "II", "III", "IV", "V"]:
            clean_words.append(w.upper())
        elif w.lower() in ["de", "y", "en", "el", "la", "los", "las"]:
            clean_words.append(w.lower())
        else:
            clean_words.append(w.capitalize())
    return " ".join(clean_words).strip()

def is_institutional_survey_or_announcement(title: str, subject: str = "") -> bool:
    """Determina si un correo es una encuesta, aviso institucional o spam no evaluativo."""
    text = f"{title} {subject}".lower()
    spam_phrases = [
        "evaluación de percepción", "evaluacion de percepción",
        "evaluación docente", "evaluacion docente",
        "agenda ucm", "ucm global", "convocatoria", "voces ucm",
        "encuesta de satisfacción", "percepción de la docencia",
        "docencia de pregrado"
    ]
    return any(p in text for p in spam_phrases)

def parse_task_from_email(msg: Dict) -> Optional[Dict]:
    """
    Analiza un correo y determina si contiene una tarea evaluada con fecha de vencimiento.
    """
    subj = msg.get("subject", "")
    content = msg.get("content", "")
    full_text = f"{subj}\n{content}"
    low = full_text.lower()

    if not any(k in low for k in KEYWORDS_ACADEMIC):
        return None

    # Filtrar encuestas y avisos institucionales que no son tareas ni evaluaciones reales
    if is_institutional_survey_or_announcement(subj, content):
        return None

    # Detectar curso
    course_name = "Universidad"
    course_m = re.search(r'\((SAN MIGUEL[^)]+)\)\s*([^|\n]+)', full_text)
    if course_m:
        course_name = course_m.group(2).strip()
    elif "iej223" in low or "estadística" in low or "estadistica" in low:
        course_name = "Estadística Aplicada"
    elif "iej224" in low or "desarrollo personal" in low:
        course_name = "Desarrollo Personal y Liderazgo"
    elif "costos" in low:
        course_name = "Gestión de Costos"

    course_name = clean_course_name(course_name)

    # Detectar título de la tarea
    task_title = None
    if "ficha de costos" in low:
        task_title = "Ficha de Costos"
    elif "actividad decimas" in low:
        task_title = "Actividad Décimas"
    elif "informe fábrica de metal" in low or "informe fabrica de metal" in low:
        task_title = "Informe Fábrica de Metal"
    elif "presentación fábrica de metal" in low or "presentacion fabrica de metal" in low:
        task_title = "Presentación Fábrica de Metal"
    else:
        title_m = re.search(r'(Tarea\s*\d+|Informe\s*\d+|Certamen\s*\d+|Evaluación\s*\d+|Actividad\s*[a-zA-Z0-9áéíóúÁÉÍÓÚ]+)', full_text, re.IGNORECASE)
        if title_m:
            task_title = title_m.group(1).strip()
        else:
            task_title = subj.replace("Vencida:", "").replace("RECORDATORIO", "").strip()

    # Si el título resultante es encuesta o aviso institucional, descartar
    if is_institutional_survey_or_announcement(task_title, subj):
        return None

    # Detectar estado
    if "usted ha realizado su entrega" in low or "entrega realizada" in low:
        status = "ENTREGADA"
    elif "vencida" in low or "plazo vencido" in low:
        status = "VENCIDA"
    else:
        status = "PENDIENTE"

    # Detectar fecha
    due_str = "Por confirmar"
    date_m = re.search(r'(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)?\s*,?\s*(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})(?:\s*,\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?|\d{1,2}:\d{2}))?', full_text, re.IGNORECASE)
    if date_m:
        due_str = date_m.group(0).strip()
    elif "en 7 días" in low:
        due_str = "En 7 días (revisar detalle)"

    return {
        "title": task_title,
        "course": course_name,
        "due_date_str": due_str,
        "status": status,
        "source": f"Apple Mail ({msg['account']})",
        "subject": subj,
        "detected_at": datetime.now().isoformat()
    }

def deduplicate_tasks(tasks: List[Dict]) -> List[Dict]:
    """
    Desduplica tareas comparando título normalizado y curso.
    """
    seen = {}
    deduped = []

    for t in tasks:
        # Clave canónica: ej "tarea 2_estadistica aplicada"
        clean_title = re.sub(r'[^a-zA-Z0-9]+', '', t.get("title", "").lower())
        clean_course = re.sub(r'[^a-zA-Z0-9]+', '', t.get("course", "").lower())
        key = f"{clean_title}_{clean_course}"

        if key in seen:
            # Si ya existía, priorizar estado más reciente o actualizar información
            existing = seen[key]
            if existing.get("status") != "COMPLETADA" and t.get("status") == "VENCIDA":
                existing["status"] = "VENCIDA"
            if t.get("due_date_str") and existing.get("due_date_str") == "Por confirmar":
                existing["due_date_str"] = t["due_date_str"]
        else:
            seen[key] = t
            deduped.append(t)

    return deduped

def update_pending_tasks_storage(tasks: List[Dict]):
    """
    Guarda las tareas desduplicadas en JSON y genera el archivo Markdown ordenado.
    """
    os.makedirs(MEMORIA_DIR, exist_ok=True)

    # 1. Guardar en JSON
    with open(TAREAS_JSON, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks, "last_updated": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)

    # 2. Generar archivo Markdown
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_content = [
        f"# 📋 Tareas Pendientes y Evaluaciones Académicas",
        f"**Última sincronización unificada:** `{now_str}`",
        f"**Fuentes monitoreadas:** `el correo institucional` (Exchange), `el correo personal` (Google) y Moodle.\n",
        f"---",
        f"\n## Resumen de Tareas Activas\n",
        f"| Estado | Tarea | Asignatura / Curso | Fecha Límite | Fuente |",
        f"|---|---|---|---|---|"
    ]

    for t in tasks:
        st = t.get("status", "PENDIENTE")
        badge = "🔴 VENCIDA" if st == "VENCIDA" else ("🟡 PENDIENTE" if st == "PENDIENTE" else "🟢 COMPLETADA")
        md_content.append(
            f"| {badge} | **{t.get('title')}** | {t.get('course')} | `{t.get('due_date_str')}` | {t.get('source')} |"
        )

    md_content.append("\n---\n")
    md_content.append("## Detalle de Entregas y Recomendaciones")
    for t in tasks:
        md_content.append(f"\n### 📌 {t.get('title')} - {t.get('course')}")
        md_content.append(f"- **Vencimiento:** `{t.get('due_date_str')}`")
        md_content.append(f"- **Estado:** `{t.get('status')}`")
        md_content.append(f"- **Detección:** {t.get('source')} - *{t.get('subject', '')}*")

    with open(TAREAS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_content))

def sync_tasks_to_iphone_reminders(tasks: List[Dict]):
    """
    Sincroniza tareas pendientes activas hacia Apple Reminders (iPhone).
    """
    existing_rems = list_apple_reminders("Tareas")
    existing_titles = {r["title"].lower().strip() for r in existing_rems}

    for t in tasks:
        if t.get("status") == "PENDIENTE":
            task_title = f"{t.get('title')} - {t.get('course')}"
            if task_title.lower().strip() not in existing_titles:
                notes = f"Fecha de entrega: {t.get('due_date_str')}\nDetectado por Life OS en {t.get('source')}"
                create_apple_reminder(task_title, notes=notes, list_name="Tareas")

def run_academic_sync() -> Dict:
    """
    Ejecuta el ciclo completo de sincronización de correos y tareas.
    """
    print("[SYNC] Iniciando escaneo de correos institucionales y personales...")
    academic_msgs = scan_exchange_academic(20) + scan_google_academic(15)

    detected = []
    for m in academic_msgs:
        t = parse_task_from_email(m)
        if t:
            detected.append(t)

    # Cargar tareas previas existentes para no perder tareas ya registradas manualmente
    prev_data = {}
    if os.path.exists(TAREAS_JSON):
        try:
            with open(TAREAS_JSON, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
        except Exception:
            pass
    raw_prev_tasks = prev_data.get("tasks", [])
    prev_tasks = []
    for pt in raw_prev_tasks:
        p_title = pt.get("title", "")
        p_subj = pt.get("subject", "")
        if not is_institutional_survey_or_announcement(p_title, p_subj):
            pt["course"] = clean_course_name(pt.get("course", ""))
            prev_tasks.append(pt)

    all_tasks = detected + prev_tasks
    deduped = deduplicate_tasks(all_tasks)
    update_pending_tasks_storage(deduped)
    sync_tasks_to_iphone_reminders(deduped)

    return {
        "success": True,
        "total_detected": len(detected),
        "total_active": len(deduped),
        "tasks": deduped,
        "md_path": TAREAS_MD
    }

if __name__ == "__main__":
    res = run_academic_sync()
    print(f"Sincronización completada: {res['total_active']} tareas unificadas en {res['md_path']}")
