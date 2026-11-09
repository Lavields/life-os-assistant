#!/usr/bin/env python3
"""
Motor de Obligaciones y Alertas Proactivas para el asistente (bot de Telegram)
- Gestiona el Briefing Matutino dinámico con eventos reales de Google Calendar y evaluaciones universidad.
- Monitorea recordatorios programados por el usuario (memoria/recordatorios_programados.json).
- Dispara alertas previas (60 min antes) de eventos y citas médicas de Google Calendar.
- Incluye en el briefing los recordatorios diarios definidos en config/config.json.
- Persistencia de alertas diarias para evitar duplicados o pérdidas si el sistema se reinicia.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.calendar_engine import get_events_for_date, list_upcoming_events, format_date_es
from scripts.academic_engine import list_pending_tasks
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME, DAILY_REMINDERS
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME, DAILY_REMINDERS

MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
CUSTOM_REMINDERS_FILE = os.path.join(MEMORIA_DIR, "recordatorios_programados.json")
SENT_ALERTS_FILE = os.path.join(MEMORIA_DIR, "alertas_enviadas_hoy.json")

def load_sent_alerts() -> Dict[str, list]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(SENT_ALERTS_FILE):
        try:
            with open(SENT_ALERTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    return data
        except Exception:
            pass
    return {"date": today_str, "alerts": []}

def save_sent_alert(alert_key: str):
    data = load_sent_alerts()
    if alert_key not in data["alerts"]:
        data["alerts"].append(alert_key)
        try:
            os.makedirs(MEMORIA_DIR, exist_ok=True)
            with open(SENT_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PROACTIVE] Error guardando alerta enviada: {e}")

def has_alert_been_sent(alert_key: str) -> bool:
    data = load_sent_alerts()
    return alert_key in data.get("alerts", [])

def in_time_window(now_dt: datetime, target_h: int, target_m: int, window_minutes: int = 15) -> bool:
    """Verifica si la hora actual está dentro de la ventana permisiva desde el target."""
    target_dt = now_dt.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
    diff = (now_dt - target_dt).total_seconds() / 60.0
    return 0 <= diff <= window_minutes

def _deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Elimina eventos duplicados por hora y temática similar."""
    seen = set()
    deduped = []
    for ev in events:
        summ = (ev.get("summary") or "").lower()
        # Normalizar para detectar duplicados obvios como 'cita con endocrinologo' y 'tengo cita con endocrinologo'
        norm = re.sub(r'^(tengo|hay|cita con el|cita con)\s*', '', summ).strip()
        time_str = ev.get("time", "")
        key = f"{norm}_{time_str}"
        if key not in seen:
            seen.add(key)
            deduped.append(ev)
    return deduped

def clean_course_display(ramo: str) -> str:
    """Limpia códigos de curso, secciones y mayúsculas excesivas a un formato natural."""
    if not ramo:
        return "la U"
    ramo = re.sub(r'-S\d+', '', ramo)
    ramo = re.sub(r'\[.*?\]', '', ramo)
    ramo = re.sub(r'\(.*?\)', '', ramo).strip()
    if not ramo or ramo.lower() in ["ucm pregrado", "pregrado", "ucm"]:
        return "la U"
    words = ramo.split()
    clean_words = []
    for w in words:
        if w.upper() in ["I", "II", "III", "IV", "V"]:
            clean_words.append(w.upper())
        elif w.lower() in ["de", "y", "en", "el", "la", "los", "las"]:
            clean_words.append(w.lower())
        else:
            clean_words.append(w.capitalize())
    clean_name = " ".join(clean_words).strip()
    if "estadística" in clean_name.lower():
        return "Estadística"
    if "desarrollo personal" in clean_name.lower():
        return "Desarrollo Personal"
    if "costos" in clean_name.lower():
        return "Costos"
    return clean_name

def is_survey_task(title: str) -> bool:
    low = title.lower()
    return any(p in low for p in [
        "percepción", "percepcion", "evaluación docente", "evaluacion docente",
        "docencia de pregrado", "convocatoria", "agenda ucm", "ucm global", "voces ucm"
    ])

def get_high_priority_academic_tasks() -> List[Dict]:
    """Obtiene evaluaciones y entregas universitarias relevantes reales (sin encuestas)."""
    tasks = list_pending_tasks()
    relevant = []
    keywords = ["tarea", "certamen", "examen", "informe", "taller", "entrega", "presenta", "prueba"]
    for t in tasks:
        title = (t.get("titulo") or "").strip()
        if is_survey_task(title):
            continue
        if any(kw in title.lower() for kw in keywords):
            relevant.append(t)
    return relevant

def get_morning_briefing(now_dt: datetime) -> List[str]:
    """Genera el mensaje del Briefing Matutino conciso, natural y <= 15 palabras por mensaje."""
    today_str = now_dt.strftime("%Y-%m-%d")
    date_display = format_date_es(now_dt)
    weekday = now_dt.weekday()

    # 1. Eventos en Google Calendar para hoy
    today_events = _deduplicate_events(get_events_for_date(today_str))
    
    # 2. Evaluaciones próximas de la universidad
    acad_tasks = get_high_priority_academic_tasks()

    bubbles = []
    if weekday < 5:
        saludo = f"¡Buen día {USER_NAME}! ☀️ Ya arrancó este {date_display}."
    else:
        saludo = f"¡Lindo fin de semana {USER_NAME}! ☀️ Hoy es {date_display}."
    bubbles.append(saludo)

    # Bloque Calendario / Citas (máximo 15 palabras por burbuja)
    if today_events:
        for ev in today_events[:2]:
            t_msg = f"En tu calendario hoy tienes: {ev['summary']} a las {ev['time']}."
            if len(t_msg.split()) <= 15:
                bubbles.append(t_msg)
            else:
                bubbles.append(f"Hoy tienes: {ev['summary']} a las {ev['time']}.")
    else:
        bubbles.append("Hoy no tienes citas agendadas en tu calendario de Google.")

    # Bloque Universidad (formato natural, sin mayúsculas excesivas ni códigos crudos)
    if acad_tasks:
        top = acad_tasks[0]
        t_tit = top.get("titulo", "")
        t_ramo = clean_course_display(top.get("ramo", ""))
        due = top.get("fecha_limite", "")
        
        due_clean = "esta semana"
        due_low = due.lower()
        if "viernes" in due_low:
            due_clean = "este viernes"
        elif "miércoles" in due_low or "miercoles" in due_low:
            due_clean = "este miércoles"
        elif "lunes" in due_low:
            due_clean = "hoy lunes"
        elif "martes" in due_low:
            due_clean = "este martes"
        elif "jueves" in due_low:
            due_clean = "este jueves"

        bubbles.append(f"En la U: recuerda la {t_tit} de {t_ramo} para {due_clean}.")

    # Bloque de recordatorios del día (config/config.json -> daily_reminders)
    upcoming = [r for r in DAILY_REMINDERS if weekday < 5 or not r.get("weekdays_only")]
    if upcoming:
        first = sorted(upcoming, key=lambda r: r["time"])[0]
        bubbles.append(f"Primer aviso del día: {first['time']} · {first['message']}")

    return bubbles

def get_evening_briefing(now_dt: datetime) -> List[str]:
    """Genera el check-in nocturno revisando el día de mañana (<= 15 palabras)."""
    tomorrow_dt = now_dt + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    tomorrow_display = format_date_es(tomorrow_dt)

    tomorrow_events = _deduplicate_events(get_events_for_date(tomorrow_str))
    acad_tasks = get_high_priority_academic_tasks()

    bubbles = [f"Buenas noches {USER_NAME} 🌙 Hora de ir cerrando la jornada."]

    if tomorrow_events:
        for ev in tomorrow_events[:2]:
            bubbles.append(f"Mañana {tomorrow_display} tienes: {ev['summary']} a las {ev['time']}.")
    else:
        bubbles.append(f"Mañana {tomorrow_display} no tienes eventos agendados en el calendario.")

    if acad_tasks:
        top_task = acad_tasks[0]
        t_tit = top_task.get("titulo", "")
        t_ramo = clean_course_display(top_task.get("ramo", ""))
        bubbles.append(f"Acuérdate que esta semana tenemos en la mira {t_tit} de {t_ramo}.")

    return bubbles

def get_study_focus_bubbles(now_dt: datetime) -> List[str]:
    """Genera mensaje del bloque de estudio universidad (<= 15 palabras)."""
    acad_tasks = get_high_priority_academic_tasks()
    if acad_tasks:
        top = acad_tasks[0]
        t_tit = top.get("titulo", "")
        t_ramo = clean_course_display(top.get("ramo", ""))
        return [
            f"Momento de estudio: te recuerdo avanzar en {t_tit} de {t_ramo}."
        ]
    return [
        "Momento de estudio: en la universidad estás al día con tus materias."
    ]

def get_calendar_pre_alert(now_dt: datetime) -> Optional[Dict]:
    """
    Revisa si hay un evento en Google Calendar dentro de los próximos 45-65 minutos
    para enviar una alerta con 1 hora de anticipación.
    """
    today_str = now_dt.strftime("%Y-%m-%d")
    events = _deduplicate_events(get_events_for_date(today_str))
    for ev in events:
        time_str = ev.get("time", "")
        if ":" in time_str:
            try:
                parts = time_str.split(":")
                ev_h, ev_m = int(parts[0]), int(parts[1])
                ev_dt = now_dt.replace(hour=ev_h, minute=ev_m, second=0, microsecond=0)
                diff_minutes = (ev_dt - now_dt).total_seconds() / 60.0
                # Si falta entre 45 y 65 minutos
                if 45 <= diff_minutes <= 65:
                    alert_key = f"cal_pre_{today_str}_{ev.get('id', time_str)}"
                    if not has_alert_been_sent(alert_key):
                        return {
                            "key": alert_key,
                            "summary": ev.get("summary"),
                            "time": time_str,
                            "message": f"{USER_NAME}, te aviso con tiempo: en 1 hora ({time_str}) tienes **{ev.get('summary')}**."
                        }
            except Exception:
                pass
    return None

def check_and_pop_custom_reminders(now_dt: datetime) -> List[Dict]:
    """
    Revisa recordatorios personalizados guardados por el usuario
    que deban sonar en la fecha y hora actual.
    """
    if not os.path.exists(CUSTOM_REMINDERS_FILE):
        return []

    now_date_str = now_dt.strftime("%Y-%m-%d")
    now_hm = now_dt.strftime("%H:%M")

    due_reminders = []
    updated_reminders = []

    try:
        with open(CUSTOM_REMINDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            reminders = data.get("recordatorios", [])

        changed = False
        for rem in reminders:
            r_date = rem.get("fecha")
            r_time = rem.get("hora")
            r_done = rem.get("ejecutado", False)

            # Si es para hoy y la hora ya se cumplió
            if not r_done and r_date == now_date_str and r_time <= now_hm:
                rem["ejecutado"] = True
                rem["ejecutado_en"] = datetime.now().isoformat()
                due_reminders.append(rem)
                changed = True
            updated_reminders.append(rem)

        if changed:
            with open(CUSTOM_REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump({"recordatorios": updated_reminders}, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[CUSTOM REMINDERS ERROR] {e}")

    return due_reminders

def add_custom_reminder(fecha_str: str, hora_str: str, mensaje: str) -> bool:
    """Guarda un recordatorio personalizado solicitado por el usuario."""
    try:
        os.makedirs(MEMORIA_DIR, exist_ok=True)
        data = {"recordatorios": []}
        if os.path.exists(CUSTOM_REMINDERS_FILE):
            with open(CUSTOM_REMINDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

        new_rem = {
            "id": f"rem-{len(data.get('recordatorios', [])) + 1:04d}",
            "fecha": fecha_str,
            "hora": hora_str,
            "mensaje": mensaje,
            "creado_en": datetime.now().isoformat(),
            "ejecutado": False
        }
        data.setdefault("recordatorios", []).append(new_rem)
        with open(CUSTOM_REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ADD REMINDER ERROR] {e}")
        return False
