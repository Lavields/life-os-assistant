#!/usr/bin/env python3
"""
Motor de Memoria Persistente y Contexto Vital para el asistente (asistente)
- Almacena notas, recuerdos, planes futuros, comentarios y estados que el usuario comparte.
- Persiste en memoria/notas_y_recuerdos.json.
- Permite consultar memorias recientes y buscar por tema.
"""

import os
import json
from datetime import datetime
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
NOTAS_FILE = os.path.join(MEMORIA_DIR, "notas_y_recuerdos.json")

def _load_notes() -> dict:
    if os.path.exists(NOTAS_FILE):
        try:
            with open(NOTAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"recuerdos": [], "planes_futuros": [], "lugares_visitados": []}

def _save_notes(data: dict) -> bool:
    try:
        os.makedirs(MEMORIA_DIR, exist_ok=True)
        with open(NOTAS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[MEMORY ENGINE ERROR] No se pudo guardar: {e}")
        return False

def add_memory_note(contenido: str, categoria: str = "general") -> dict:
    """Guarda una nota, recuerdo o hecho importante compartido por el usuario."""
    data = _load_notes()
    entry = {
        "id": f"mem-{len(data.get('recuerdos', [])) + 1:03d}",
        "contenido": contenido.strip(),
        "categoria": categoria,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data.setdefault("recuerdos", []).append(entry)
    _save_notes(data)
    return {"success": True, "entry": entry}

def add_future_plan(descripcion: str, fecha_aproximada: str = "Pronto") -> dict:
    """Guarda un plan que el usuario comentó que hará un día futuro."""
    data = _load_notes()
    entry = {
        "id": f"plan-{len(data.get('planes_futuros', [])) + 1:03d}",
        "descripcion": descripcion.strip(),
        "fecha_estimada": fecha_aproximada,
        "creado_el": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data.setdefault("planes_futuros", []).append(entry)
    _save_notes(data)
    return {"success": True, "entry": entry}

def record_location_mention(lugar: str, comentario: str = "") -> dict:
    """Registra cuando el usuario menciona que está en algún lugar."""
    data = _load_notes()
    entry = {
        "lugar": lugar.strip(),
        "comentario": comentario.strip(),
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data.setdefault("lugares_visitados", []).append(entry)
    _save_notes(data)
    return {"success": True, "entry": entry}

def get_recent_memories(limit: int = 5) -> list:
    """Retorna los recuerdos y notas más recientes."""
    data = _load_notes()
    all_items = data.get("recuerdos", []) + data.get("planes_futuros", [])
    return all_items[-limit:]

def get_memories_summary_text() -> str:
    """Genera un resumen en texto para el system prompt de el asistente."""
    data = _load_notes()
    recuerdos = data.get("recuerdos", [])[-4:]
    planes = data.get("planes_futuros", [])[-3:]
    lugares = data.get("lugares_visitados", [])[-2:]

    parts = []
    if recuerdos:
        parts.append(f"Últimas cosas que te contó {USER_NAME}: " + "; ".join([r["contenido"] for r in recuerdos]))
    if planes:
        parts.append(f"Planes futuros de {USER_NAME}: " + "; ".join([f"{p['descripcion']} ({p['fecha_estimada']})" for p in planes]))
    if lugares:
        parts.append("Últimos lugares donde estuvo: " + "; ".join([f"{l['lugar']} ({l['fecha']})" for l in lugares]))
    return "\n".join(parts) if parts else "Sin notas adicionales registradas recientemente."

if __name__ == "__main__":
    print("--- TEST MEMORY ENGINE ---")
    add_memory_note("Almuerzo con el abuelo los domingos", "familia")
    print(get_memories_summary_text())
