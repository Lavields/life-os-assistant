#!/usr/bin/env python3
"""
Sincronizador de Moodle (calendario iCal) para el asistente
- Descarga y analiza el feed iCal de Moodle.
- Extrae evaluaciones, tareas y certámenes con fecha fatal en hora chilena.
- Sincroniza con memoria/tareas_pendientes.json para que el asistente consulte en tiempo real.
"""

import os
import sys
import json
import re
import urllib.request
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
TAREAS_FILE = os.path.join(MEMORIA_DIR, "tareas_pendientes.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")

def _load_env_url() -> str:
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("MOODLE_ICAL_URL="):
                        val = line.split("=", 1)[1].strip()
                        return val.strip('"\']')
        except Exception:
            pass
    return ""

def _parse_ical_datetime(dt_str: str) -> datetime:
    """Parsea formatos iCal como '20261105T235900Z' o '20261105T235900'."""
    clean = dt_str.replace("Z", "").strip()
    if "T" in clean:
        return datetime.strptime(clean, "%Y%m%dT%H%M%S")
    else:
        return datetime.strptime(clean, "%Y%m%d")

def parse_ical_content(content: str) -> list:
    """Parsea texto iCal y extrae eventos con sus atributos."""
    events = []
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.DOTALL)
    
    for b in blocks:
        summary_m = re.search(r"SUMMARY:(.+)", b)
        desc_m = re.search(r"DESCRIPTION:(.+)", b)
        dtstart_m = re.search(r"DTSTART(?:;[^:]+)?:([0-9TZ]+)", b)
        dtend_m = re.search(r"DTEND(?:;[^:]+)?:([0-9TZ]+)", b)
        uid_m = re.search(r"UID:(.+)", b)
        cats_m = re.search(r"CATEGORIES:(.+)", b)

        summary = summary_m.group(1).strip() if summary_m else "Sin título"
        desc = desc_m.group(1).strip() if desc_m else ""
        # Reemplazar escapes iCal
        desc = desc.replace(r"\n", " ").replace(r"\,", ",")

        dtstart_raw = dtstart_m.group(1).strip() if dtstart_m else None
        dtend_raw = dtend_m.group(1).strip() if dtend_m else dtstart_raw

        due_dt = None
        if dtend_raw:
            try:
                due_dt = _parse_ical_datetime(dtend_raw)
            except Exception:
                pass

        uid = uid_m.group(1).strip() if uid_m else ""
        course = cats_m.group(1).strip() if cats_m else "Ingeniería en Ejecución Industrial"

        events.append({
            "uid": uid,
            "title": summary,
            "course": course,
            "description": desc,
            "due_dt": due_dt,
            "due_str": due_dt.strftime("%Y-%m-%d %H:%M") if due_dt else "Sin fecha"
        })

    return events

def sync_moodle_tasks(custom_url: str = None) -> dict:
    """
    Sincroniza las tareas desde la URL de iCal de Moodle.
    Si no hay URL configurada, mantiene y valida las tareas existentes.
    """
    url = custom_url or _load_env_url()
    if not url:
        return {
            "success": False,
            "configured": False,
            "message": "Falta configurar MOODLE_ICAL_URL en .env con el enlace exportado desde el calendario de Moodle (calendar/view.php)"
        }

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LifeOSAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        events = parse_ical_content(content)
        if not events:
            return {"success": True, "configured": True, "count": 0, "message": "No se encontraron eventos en el feed de Moodle."}

        # Cargar archivo de tareas existente
        existing_data = {"tareas_academicas": [], "habitos_clave": []}
        if os.path.exists(TAREAS_FILE):
            try:
                with open(TAREAS_FILE, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                pass

        current_tasks = existing_data.get("tareas_academicas", [])
        existing_titles = {t.get("titulo", "").lower(): t for t in current_tasks}

        now = datetime.now()
        added_count = 0

        for ev in events:
            t_key = ev["title"].lower()
            if t_key not in existing_titles:
                # Determinar prioridad por fecha límite
                prioridad = "Media"
                if ev["due_dt"] and (ev["due_dt"] - now).total_seconds() < 86400 * 3:
                    prioridad = "Alta"

                new_task = {
                    "id": f"moodle-{len(current_tasks) + 1:03d}",
                    "ramo": ev["course"],
                    "titulo": ev["title"],
                    "plataforma": "Moodle",
                    "fecha_limite": ev["due_str"],
                    "prioridad": prioridad,
                    "estado": "pendiente",
                    "notas": ev["description"][:200]
                }
                current_tasks.append(new_task)
                added_count += 1

        existing_data["tareas_academicas"] = current_tasks
        os.makedirs(MEMORIA_DIR, exist_ok=True)
        with open(TAREAS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "configured": True,
            "total_events": len(events),
            "added_count": added_count,
            "message": f"Sincronización exitosa: {added_count} nuevas tareas agregadas desde Moodle."
        }
    except Exception as e:
        return {"success": False, "configured": True, "error": str(e)}

def get_weekly_academic_summary() -> dict:
    """
    Retorna un resumen estructurado de las tareas de la próxima semana para el asistente.
    """
    if os.path.exists(TAREAS_FILE):
        try:
            with open(TAREAS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    tasks = [t for t in data.get("tareas_academicas", []) if t.get("estado") != "completada"]
    if not tasks:
        return {
            "has_tasks": False,
            "summary_text": "No tienes tareas académicas pendientes registradas para esta semana, amigo lindo ✨",
            "tasks": []
        }

    formatted = []
    for t in tasks[:5]:
        prio = "🔥" if t.get("prioridad") == "Alta" else "📌"
        formatted.append(f"{prio} **{t.get('titulo')}** ({t.get('ramo')})\n  🕒 Límite: {t.get('fecha_limite')}")

    return {
        "has_tasks": True,
        "count": len(tasks),
        "summary_text": "Estas son tus tareas pendientes de la universidad para esta semana:\n\n" + "\n\n".join(formatted),
        "tasks": tasks
    }

if __name__ == "__main__":
    print("Moodle Sync Test:")
    print(get_weekly_academic_summary())
