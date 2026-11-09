#!/usr/bin/env python3
"""
Motor de Integración con Obsidian para el asistente (asistente)
- Administra y extrae información de la bóveda de Obsidian:
  ruta definida en OBSIDIAN_VAULT_DIR
- Lee checklists pendientes (- [ ]), tags (#tarea, #examen, #certamen) y notas académicas.
- Permite captura rápida de ideas, recordatorios y apuntes desde Telegram hacia Obsidian.
- Provee enlaces profundos obsidian:// para abrir notas en un toque en macOS.
"""

import os
import re
import urllib.parse
from datetime import datetime

VAULT_DIR = os.path.expanduser(os.getenv("OBSIDIAN_VAULT_DIR", "~/Documents/Obsidian Vault"))
PDF_DIR = os.path.expanduser(os.getenv("OBSIDIAN_PDF_DIR", "~/Desktop/PDF OBSIDIAN"))
VAULT_NAME = "Mi Vault"

def is_vault_available() -> bool:
    return os.path.exists(VAULT_DIR) and os.path.isdir(VAULT_DIR)

def scan_pending_tasks_in_vault() -> list:
    """
    Escanea recursivamente los archivos Markdown en la bóveda
    buscando checkboxes pendientes: - [ ]
    """
    if not is_vault_available():
        return []

    tasks = []
    task_regex = re.compile(r"^\s*-\s*\[ \]\s*(.+)$")

    for root, _, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, VAULT_DIR)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            m = task_regex.match(line)
                            if m:
                                task_text = m.group(1).strip()
                                # Detectar prioridad por tags
                                is_urgent = any(t in task_text.lower() for t in ["#urgente", "#examen", "#certamen", "entrega", "fatal"])
                                tasks.append({
                                    "task": task_text,
                                    "file": file,
                                    "rel_path": rel_path,
                                    "line": line_num,
                                    "is_urgent": is_urgent,
                                    "obsidian_uri": f"obsidian://open?vault={urllib.parse.quote(VAULT_NAME)}&file={urllib.parse.quote(rel_path[:-3])}"
                                })
                except Exception:
                    pass

    return tasks

def search_notes(query: str, max_results: int = 5) -> list:
    """
    Busca palabras clave dentro de las notas de la bóveda.
    """
    if not is_vault_available() or not query.strip():
        return []

    results = []
    q_lower = query.lower()

    for root, _, files in os.walk(VAULT_DIR):
        if ".obsidian" in root:
            continue
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, VAULT_DIR)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if q_lower in content.lower() or q_lower in file.lower():
                            # Extraer un extracto relevante
                            idx = content.lower().find(q_lower)
                            start = max(0, idx - 60)
                            end = min(len(content), idx + 140)
                            snippet = content[start:end].replace("\n", " ").strip()
                            results.append({
                                "file": file,
                                "rel_path": rel_path,
                                "snippet": f"...{snippet}...",
                                "obsidian_uri": f"obsidian://open?vault={urllib.parse.quote(VAULT_NAME)}&file={urllib.parse.quote(rel_path[:-3])}"
                            })
                            if len(results) >= max_results:
                                return results
                except Exception:
                    pass

    return results

def append_to_daily_note(note_text: str, category: str = "Apunte") -> dict:
    """
    Agrega una nota o apunte a la nota diaria de Obsidian (Diario/YYYY-MM-DD.md).
    """
    if not is_vault_available():
        return {"success": False, "error": "Bóveda de Obsidian no encontrada"}

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    
    daily_folder = os.path.join(VAULT_DIR, "Diario")
    os.makedirs(daily_folder, exist_ok=True)
    daily_file = os.path.join(daily_folder, f"{date_str}.md")

    rel_path = f"Diario/{date_str}"
    is_new = not os.path.exists(daily_file)

    line_to_add = f"\n- **[{time_str}] ({category}):** {note_text.strip()}\n"

    try:
        with open(daily_file, "a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# 📅 Diario y Captura Rápida: {date_str}\n\n## Apuntes y Registro Diario\n")
            f.write(line_to_add)

        obsidian_uri = f"obsidian://open?vault={urllib.parse.quote(VAULT_NAME)}&file={urllib.parse.quote(rel_path)}"
        return {
            "success": True,
            "file": f"{date_str}.md",
            "rel_path": rel_path,
            "obsidian_uri": obsidian_uri
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_obsidian_tasks_summary() -> dict:
    """
    Genera un resumen de tareas pendientes en Obsidian para el asistente.
    """
    tasks = scan_pending_tasks_in_vault()
    if not tasks:
        return {
            "has_tasks": False,
            "text": "Revisé tu bóveda de Obsidian y no encontré tareas pendientes sin marcar con `- [ ]`, amigo lindo ✨",
            "tasks": []
        }

    formatted = []
    for t in tasks[:5]:
        prio = "🔥" if t["is_urgent"] else "📝"
        formatted.append(f"{prio} {t['task']}\n   📌 *Nota:* `{t['file']}`")

    return {
        "has_tasks": True,
        "count": len(tasks),
        "text": f"Encontré {len(tasks)} tareas pendientes anotadas en tu Obsidian:\n\n" + "\n\n".join(formatted),
        "tasks": tasks
    }

if __name__ == "__main__":
    print("Obsidian Vault Available:", is_vault_available())
    print("Pending Tasks Summary:")
    print(get_obsidian_tasks_summary())
