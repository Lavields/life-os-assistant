#!/usr/bin/env python3
"""
Motor Académico universidad para el asistente (asistente)
- Administra tareas, entregas, evaluaciones y ramos del usuario.
- Persiste datos en memoria/tareas_pendientes.json.
- Permite consultar tareas pendientes, la más próxima, agregar nuevas tareas y marcarlas como completadas.
"""

import os
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
TAREAS_FILE = os.path.join(MEMORIA_DIR, "tareas_pendientes.json")

def _load_data() -> dict:
    if os.path.exists(TAREAS_FILE):
        try:
            with open(TAREAS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Normalizar si viene del formato tasks de academic_scanner
                    if "tasks" in data:
                        raw_tasks = data["tasks"]
                        norm = []
                        for t in raw_tasks:
                            title = t.get("title") or t.get("titulo", "")
                            status = (t.get("status") or t.get("estado", "")).upper()
                            if status not in ["VENCIDA", "COMPLETADA"]:
                                norm.append({
                                    "id": title,
                                    "ramo": t.get("course") or t.get("ramo", "universidad Pregrado"),
                                    "titulo": title,
                                    "plataforma": t.get("source", "Moodle / Correo"),
                                    "fecha_limite": t.get("due_date_str") or t.get("fecha_limite", "Por confirmar"),
                                    "prioridad": "Alta" if any(w in title.lower() for w in ["tarea", "presenta", "evalua", "certamen"]) else "Media",
                                    "estado": "pendiente",
                                    "notas": t.get("subject", "")
                                })
                        data["tareas_academicas"] = norm
                    return data
        except Exception as e:
            print(f"[ACADEMIC ENGINE LOAD ERROR] {e}")
    return {"tareas_academicas": [], "habitos_clave": []}

def _save_data(data: dict) -> bool:
    try:
        os.makedirs(MEMORIA_DIR, exist_ok=True)
        with open(TAREAS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ACADEMIC ENGINE ERROR] No se pudo guardar: {e}")
        return False

def list_pending_tasks(ramo: str = None) -> list:
    """Retorna la lista de tareas pendientes, opcionalmente filtrada por ramo."""
    data = _load_data()
    tasks = [t for t in data.get("tareas_academicas", []) if t.get("estado") != "completada"]
    if ramo:
        tasks = [t for t in tasks if ramo.lower() in t.get("ramo", "").lower()]
    return tasks

def get_closest_due_task() -> dict:
    """Encuentra la tarea o entrega más próxima."""
    tasks = list_pending_tasks()
    if not tasks:
        return {"found": False}
    # Prioridad alta primero o la primera registrada
    altas = [t for t in tasks if t.get("prioridad") == "Alta"]
    target = altas[0] if altas else tasks[0]
    return {"found": True, "task": target}

def add_academic_task(ramo: str, titulo: str, fecha_limite: str, prioridad: str = "Media", notas: str = "") -> dict:
    """Agrega una nueva tarea a la memoria académica."""
    data = _load_data()
    new_id = f"tarea-{len(data.get('tareas_academicas', [])) + 1:03d}"
    new_task = {
        "id": new_id,
        "ramo": ramo or "Ingeniería en Ejecución Industrial",
        "titulo": titulo,
        "plataforma": "Moodle / Presencial",
        "fecha_limite": fecha_limite or "Por definir",
        "prioridad": prioridad or "Media",
        "estado": "pendiente",
        "notas": notas or "",
        "creado_el": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data.setdefault("tareas_academicas", []).append(new_task)
    _save_data(data)
    return {"success": True, "task": new_task}

def mark_task_completed(identifier: str) -> dict:
    """Marca una tarea como completada por ID o coincidencia en título/ramo."""
    data = _load_data()
    ident_lower = identifier.lower().strip()
    found = False
    updated_title = ""
    for t in data.get("tareas_academicas", []):
        if t.get("id") == identifier or ident_lower in t.get("titulo", "").lower():
            t["estado"] = "completada"
            t["completada_el"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            found = True
            updated_title = t.get("titulo")
            break
    if found:
        _save_data(data)
        return {"success": True, "titulo": updated_title}
    return {"success": False, "error": "No se encontró la tarea especificada"}

def add_routine_item(nombre: str, hora: str, tipo: str = "diario") -> dict:
    """Agrega un hábito o rutina a la memoria."""
    data = _load_data()
    new_id = f"hab-{len(data.get('habitos_clave', [])) + 1:03d}"
    new_hab = {
        "id": new_id,
        "nombre": nombre,
        "hora": hora or "Por definir",
        "tipo": tipo
    }
    data.setdefault("habitos_clave", []).append(new_hab)
    _save_data(data)
    return {"success": True, "habit": new_hab}

def get_academic_overview_text() -> str:
    """Genera un resumen en texto claro de las tareas pendientes."""
    tasks = list_pending_tasks()
    if not tasks:
        return "No tienes tareas pendientes registradas en la U por ahora. Todo al día y despejado."
    lines = []
    for i, t in enumerate(tasks, 1):
        lines.append(f"{i}. **{t.get('titulo')}** ({t.get('ramo')}) - Fecha: {t.get('fecha_limite')} [Prioridad {t.get('prioridad')}]")
        if t.get("notas"):
            lines.append(f"   *Detalle: {t.get('notas')}*")
    return "\n".join(lines)

if __name__ == "__main__":
    print("--- TEST ACADEMIC ENGINE ---")
    print(get_academic_overview_text())
    closest = get_closest_due_task()
    print("Closest task:", closest)
