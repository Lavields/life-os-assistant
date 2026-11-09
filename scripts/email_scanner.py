#!/usr/bin/env python3
"""
Módulo de Monitoreo de Correo (Universidad y Personal) para asistente
- Lee directamente a través de Apple Mail en macOS (sin almacenar contraseñas ni tokens frágiles).
- Rastrea bandejas de entrada personales y universitarias.
- Identifica tareas, entregas, evaluaciones o avisos de profesores.
- Cita siempre la fuente exacta (Cuenta, Remitente y Fecha).
"""

import os
import subprocess
from datetime import datetime

KEYWORDS_ACADEMIC = [
    "ucm", "moodle", "tarea", "entrega", "evaluacion", "evaluación",
    "examen", "profesor", "profesora", "clase", "informe", "proyecto",
    "nota", "certamen", "ayudantia", "ayudantía", "laboratorio"
]

def scan_recent_emails(max_messages_per_account: int = 30) -> list:
    """
    Escanea cuentas configuradas en Apple Mail (Google personal, iCloud o universidad).
    Retorna una lista estructurada de correos relevantes con su fuente citada.
    """
    script = f'''
tell application "Mail"
    set results to {{}}
    repeat with acc in accounts
        set accName to name of acc
        try
            set ibox to mailbox "INBOX" of acc
            set totalCount to count of messages of ibox
            set checkCount to {max_messages_per_account}
            if totalCount < checkCount then
                set checkCount to totalCount
            end if
            
            if checkCount > 0 then
                set msgList to (messages 1 thru checkCount of ibox)
                repeat with m in msgList
                    set subj to subject of m
                    set sndr to sender of m
                    set dt to (date received of m as text)
                    set end of results to (accName & "|||" & subj & "|||" & sndr & "|||" & dt)
                end repeat
            end if
        end try
    end repeat
    return results
end tell
'''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[MAIL ERROR] {res.stderr}")
        return []

    output = res.stdout.strip()
    if not output:
        return []

    # Parsear salidas separadas por coma en AppleScript
    # AppleScript returns a comma-separated list of strings
    items = output.split(", ")
    parsed_emails = []

    for item in items:
        parts = item.split("|||")
        if len(parts) == 4:
            acc, subj, sndr, dt = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
            low_text = f"{subj} {sndr}".lower()
            is_relevant = any(k in low_text for k in KEYWORDS_ACADEMIC)

            parsed_emails.append({
                "account": acc,
                "subject": subj,
                "sender": sndr,
                "date": dt,
                "is_academic": is_relevant
            })

    return parsed_emails

def get_academic_summary() -> dict:
    """
    Genera un informe para el Coach con las tareas detectadas y su fuente.
    """
    all_emails = scan_recent_emails(35)
    academic = [m for m in all_emails if m["is_academic"]]

    if academic:
        formatted = []
        for a in academic[:5]:
            formatted.append(
                f"• **{a['subject']}**\n"
                f"  📌 *Fuente:* {a['account']} | *De:* `{a['sender']}`\n"
                f"  🕒 *Fecha:* {a['date']}"
            )
        return {
            "has_urgent": True,
            "text": "Encontré estos correos sobre materias o la universidad:\n\n" + "\n\n".join(formatted),
            "count": len(academic)
        }
    else:
        # Si no hay correos con palabras clave académicas recientes
        latest_str = ""
        if all_emails:
            latest = all_emails[0]
            latest_str = f"Último correo recibido: *{latest['subject']}*\n📌 *Fuente:* Cuenta `{latest['account']}` (De: `{latest['sender']}`)"

        return {
            "has_urgent": False,
            "text": "Revisé tus bandejas de correo (Personal y vinculadas) y no hay avisos nuevos de tareas o entregas de la universidad en las últimas horas.\n\n" + latest_str,
            "count": 0
        }

if __name__ == "__main__":
    summary = get_academic_summary()
    print("Academic Summary:")
    print(summary["text"])
