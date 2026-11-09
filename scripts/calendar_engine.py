#!/usr/bin/env python3
"""
Motor de Integración con Google Calendar para el asistente (asistente)
- Utiliza gcalendar CLI autenticado con la cuenta de Google de el usuario (el correo personal).
- Permite consultar eventos próximos, el día más próximo con actividades,
  eventos por fecha, agendar, modificar y cancelar compromisos con zona horaria de Chile (America/Santiago, UTC-3).
"""

import os
import sys
import json
import subprocess
import re
from datetime import datetime, timedelta
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME

LANGUAGE_SERVER_BIN = "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
GCALENDAR_FALLBACK = os.getenv("GCALENDAR_BIN", os.path.expanduser("~/.gemini/antigravity/bin/gcalendar"))

DIAS_ES = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo"
}

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def format_date_es(dt: datetime) -> str:
    """Formatea una fecha en español natural: 'Lunes 02 de Noviembre de 2026'."""
    dia_nom = DIAS_ES.get(dt.weekday(), "")
    mes_nom = MESES_ES.get(dt.month, "")
    return f"{dia_nom} {dt.day:02d} de {mes_nom} de {dt.year}"

def _run_gcalendar(args: list) -> dict:
    if os.path.exists(LANGUAGE_SERVER_BIN):
        cmd = [LANGUAGE_SERVER_BIN, "plugin-cli", "gcalendar"] + args
    elif os.path.exists(GCALENDAR_FALLBACK):
        cmd = [GCALENDAR_FALLBACK] + args
    else:
        cmd = ["gcalendar"] + args
    env = os.environ.copy()
    env["PATH"] = f"{os.path.dirname(GCALENDAR_FALLBACK)}:{env.get('PATH', '')}"
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            try:
                return {"success": True, "data": json.loads(res.stdout), "raw": res.stdout}
            except Exception:
                return {"success": True, "raw": res.stdout, "data": None}
        return {"success": False, "error": res.stderr.strip() or res.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_upcoming_events(max_results: int = 15) -> list:
    """Obtiene los próximos eventos reales en el calendario de el usuario."""
    res = _run_gcalendar(["readonly", "events", "--max", str(max_results), "--json"])
    if not res["success"] or not isinstance(res.get("data"), list):
        return []

    events = []
    now = datetime.now()

    for item in res["data"]:
        summary = item.get("summary", "Sin título")
        start = item.get("start", {})
        start_date_str = start.get("dateTime") or start.get("date")
        if not start_date_str:
            continue

        is_all_day = "T" not in start_date_str
        try:
            if is_all_day:
                dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d")
            else:
                clean_iso = start_date_str.split("+")[0].split("Z")[0]
                dt = datetime.strptime(clean_iso[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            continue

        events.append({
            "id": item.get("id"),
            "summary": summary,
            "start_dt": dt,
            "is_all_day": is_all_day,
            "html_link": item.get("htmlLink", ""),
            "date_display": format_date_es(dt),
            "time_display": "Todo el día" if is_all_day else dt.strftime("%H:%M")
        })

    events.sort(key=lambda x: x["start_dt"])
    return events

def get_next_upcoming_event() -> dict:
    """Encuentra el evento o compromiso más próximo a la fecha y hora actual."""
    events = list_upcoming_events(20)
    now = datetime.now()
    future = [e for e in events if e["start_dt"] >= now.replace(hour=0, minute=0, second=0)]
    if future:
        target = future[0]
        delta_days = (target["start_dt"].date() - now.date()).days
        return {
            "found": True,
            "event": target,
            "days_until": delta_days
        }
    return {"found": False}

def get_events_for_date(date_str: str) -> list:
    """Consulta eventos para una fecha específica (YYYY-MM-DD)."""
    res = _run_gcalendar(["readonly", "events", "--date", date_str, "--json"])
    if not res["success"] or not isinstance(res.get("data"), list):
        return []
    result = []
    for item in res["data"]:
        summary = item.get("summary", "Sin título")
        start = item.get("start", {})
        start_time = start.get("dateTime")
        time_str = "Todo el día"
        if start_time and "T" in start_time:
            time_str = start_time.split("T")[1][:5]
        result.append({
            "id": item.get("id"),
            "summary": summary,
            "time": time_str,
            "link": item.get("htmlLink", "")
        })
    return result

def create_calendar_event(summary: str, start_iso: str, end_iso: str = None, description: str = "") -> dict:
    """
    Crea un evento en el calendario de Google de el usuario.
    start_iso: '2026-11-03T15:00:00-03:00' o '2026-11-03'
    """
    args = ["mutate", "create", "--summary", summary]
    if "T" in start_iso:
        args.extend(["--start", start_iso])
        if end_iso:
            args.extend(["--end", end_iso])
        else:
            try:
                base_dt = datetime.strptime(start_iso[:19], "%Y-%m-%dT%H:%M:%S")
                end_dt = base_dt + timedelta(hours=1)
                tz_suffix = start_iso[19:] if len(start_iso) > 19 else "-03:00"
                args.extend(["--end", f"{end_dt.strftime('%Y-%m-%dT%H:%M:%S')}{tz_suffix}"])
            except Exception:
                args.extend(["--end", start_iso])
    else:
        args.extend(["--start", start_iso, "--end", end_iso or start_iso])

    if description:
        args.extend(["--description", description])

    return _run_gcalendar(args)

def update_calendar_event(event_id: str, new_start_iso: str = None, new_end_iso: str = None, new_summary: str = None) -> dict:
    """Modifica fecha, hora o título de un evento existente en Google Calendar."""
    args = ["mutate", "update", event_id]
    if new_start_iso:
        args.extend(["--start", new_start_iso])
    if new_end_iso:
        args.extend(["--end", new_end_iso])
    if new_summary:
        args.extend(["--summary", new_summary])
    return _run_gcalendar(args)

def delete_calendar_event(event_id: str) -> dict:
    """Elimina un evento del calendario."""
    return _run_gcalendar(["mutate", "delete", event_id])

def get_next_free_slots(duration: str = "1h") -> dict:
    """Busca los próximos bloques libres en la agenda de el usuario."""
    res = _run_gcalendar(["readonly", "next-free", "--duration", duration, "--json"])
    return res

def parse_relative_date(text: str):
    """Detecta fechas relativas en texto natural: hoy, mañana, pasado mañana, días de la semana."""
    now = datetime.now()
    lower = text.lower()
    if "pasado mañana" in lower or "pasado manana" in lower:
        return (now + timedelta(days=2)).date()
    elif "mañana" in lower or "manana" in lower:
        return (now + timedelta(days=1)).date()
    elif "hoy" in lower:
        return now.date()

    dias = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
    }
    for nombre, dia_idx in dias.items():
        if f"el {nombre}" in lower or f"este {nombre}" in lower or f"próximo {nombre}" in lower or f"proximo {nombre}" in lower or lower.strip() == nombre:
            cur_idx = now.weekday()
            diff = (dia_idx - cur_idx) % 7
            if diff == 0:
                diff = 7
            return (now + timedelta(days=diff)).date()

    m_exp = re.search(r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)', lower)
    if m_exp:
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        dia = int(m_exp.group(1))
        mes = meses.index(m_exp.group(2)) + 1
        year = now.year
        try:
            target_dt = datetime(year, mes, dia).date()
            if target_dt < now.date():
                target_dt = datetime(year + 1, mes, dia).date()
            return target_dt
        except Exception:
            pass

    return None

def parse_time_from_text(text: str):
    """Detecta hora en formatos comunes: 'a las 15:30', 'a las 3pm', 'a las 10 am', etc."""
    lower = text.lower()
    m = re.search(r'a\s+las\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|hrs|horas)?', lower)
    if m:
        h = int(m.group(1))
        mins = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mins:02d}"
    return None

def parse_and_create_event_from_text(text: str) -> dict:
    """
    Parsea una orden en lenguaje natural de el usuario para agendar en Google Calendar.
    Ej: 'guarda en mi calendario que mañana a las 3pm tengo cita con el endocrinólogo'
    """
    target_date = parse_relative_date(text)
    time_str = parse_time_from_text(text)

    clean = text
    prefixes = [
        "guarda en mi calendario que", "guarda en mi calendario",
        "agenda en mi calendario que", "agenda en mi calendario",
        "pon en mi calendario que", "pon en mi calendario",
        "anota en mi calendario que", "anota en mi calendario",
        "agrega a mi calendario que", "agrega a mi calendario",
        "agéndame que", "agéndame", "agendame"
    ]
    for p in prefixes:
        if clean.lower().startswith(p):
            clean = clean[len(p):].strip()
            break

    clean_summary = re.sub(r'(mañana|manana|hoy|pasado mañana|el (lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)|a\s+las\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|hrs|horas)?)', '', clean, flags=re.IGNORECASE)
    clean_summary = re.sub(r'^(tengo\s+que\s+|tengo\s+|hay\s+|que\s+|de\s+)', '', clean_summary.strip(), flags=re.IGNORECASE).strip()
    clean_summary = re.sub(r'\s+', ' ', clean_summary).strip(' ,.-')
    if not clean_summary:
        clean_summary = f"Compromiso agendado por {USER_NAME}"
    else:
        clean_summary = clean_summary[0].upper() + clean_summary[1:]

    date_to_use = target_date or (datetime.now() + timedelta(days=1)).date()

    if time_str:
        start_iso = f"{date_to_use.strftime('%Y-%m-%d')}T{time_str}:00-03:00"
    else:
        start_iso = date_to_use.strftime('%Y-%m-%d')

    res = create_calendar_event(clean_summary, start_iso, description=f"Creado vía asistente {ASSISTANT_NAME}")
    dt_comb = datetime.combine(date_to_use, datetime.min.time())
    return {
        "success": res.get("success", False),
        "summary": clean_summary,
        "date_display": format_date_es(dt_comb),
        "time_display": time_str or "Todo el día",
        "raw_res": res
    }

if __name__ == "__main__":
    print("--- PRUEBA GOOGLE CALENDAR ---")
    next_ev = get_next_upcoming_event()
    print("Próximo evento:", next_ev)
