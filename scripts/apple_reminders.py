#!/usr/bin/env python3
"""
Módulo de Integración Nativa con Apple Reminders (Recordatorios de macOS e iOS)
- Sincroniza directamente con iCloud para que los recordatorios aparezcan en el iPhone de el usuario.
- Permite crear, listar y marcar recordatorios completados con fecha límite y notas.
"""

import subprocess
import json
from datetime import datetime
from typing import Optional, List, Dict

def create_apple_reminder(title: str, due_date: Optional[datetime] = None, notes: str = "", list_name: str = "Tareas") -> dict:
    """
    Crea un recordatorio en Apple Reminders sincronizado con iCloud y el iPhone.
    """
    date_script = ""
    if due_date:
        # Formato de fecha para AppleScript según la localización del sistema
        day = due_date.day
        month = due_date.month
        year = due_date.year
        hour = due_date.hour
        minute = due_date.minute
        date_script = f'set d to current date\nset day of d to {day}\nset month of d to {month}\nset year of d to {year}\nset hours of d to {hour}\nset minutes of d to {minute}\nset seconds of d to 0\nset due date of newRem to d'

    clean_title = title.replace('"', '\\"').strip()
    clean_notes = notes.replace('"', '\\"').strip()

    script = f'''
tell application "Reminders"
    set targetList to list "{list_name}"
    tell targetList
        set newRem to make new reminder with properties {{name:"{clean_title}", body:"{clean_notes}"}}
        {date_script}
    end tell
    return id of newRem
end tell
'''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            rem_id = res.stdout.strip()
            return {
                "success": True,
                "id": rem_id,
                "title": title,
                "list": list_name,
                "due_date": due_date.isoformat() if due_date else None
            }
        else:
            return {"success": False, "error": res.stderr.strip() or "Error desconocido al crear recordatorio"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_apple_reminders(list_name: str = "Tareas", include_completed: bool = False) -> List[Dict]:
    """
    Lista los recordatorios existentes en la lista indicada de forma ultra-rápida.
    """
    script = f'''
tell application "Reminders"
    set resText to ""
    try
        set tList to list "{list_name}"
        set nameList to name of reminders of tList
        set compList to completed of reminders of tList
        repeat with i from 1 to count of nameList
            set rName to item i of nameList
            set isComp to item i of compList
            if {str(include_completed).lower()} or not isComp then
                set resText to resText & rName & "|||" & (isComp as text) & "###REM###"
            end if
        end repeat
    end try
    return resText
end tell
'''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return []
        output = res.stdout.strip()
        if not output:
            return []
        
        items = output.split("###REM###")
        reminders = []
        for it in items:
            parts = it.split("|||")
            if len(parts) >= 2:
                reminders.append({
                    "title": parts[0].strip(),
                    "body": "",
                    "completed": parts[1].strip().lower() == "true"
                })
        return reminders
    except Exception as e:
        print(f"[REMINDERS ERROR] {e}")
        return []

if __name__ == "__main__":
    print("Probando conexión con Apple Reminders...")
    rems = list_apple_reminders("Tareas")
    print(f"Recordatorios actuales en Tareas ({len(rems)}):", rems)
