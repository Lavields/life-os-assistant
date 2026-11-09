#!/usr/bin/env python3
"""
Módulo de Monitoreo de Alta Señal para Gmail (el correo personal)
Filtra estrictamente el correo eliminando spam, marketing y bolsas de empleo masivas.

LO QUE SÍ AVISA:
1. TRABAJO DIRECTO: Contactos de personas, empresas o reclutadores reales (excluye portales).
2. UNIVERSIDAD: Avisos de profesores, escuela o temas universidad.
3. MENSAJES DIRECTOS: Correos 1 a 1 de personas reales o empresas con trámites individuales.
4. DINERO RECIBIDO: Notificaciones bancarias de transferencias entrantes, depósitos o abonos.
5. PAQUETES Y SEGUIMIENTO: Estado real de despacho ("en camino", "llega hoy") de Mercado Libre, AliExpress o couriers.

LO QUE FILTRA Y DESECHA:
- Portales de empleo masivo: Computrabajo, Laborum, Indeed, JobLeads, beBee, Chiletrabajos, etc.
- Correos promocionales: Ofertas, Cyber, 11.11, descuentos, cupones, newsletters.
- Videojuegos y ocio: Twitch, Steam, Google Play, etc.
- Remitentes automáticos no-reply que sean de marketing masivo.
"""

import os
import sys
import re
import json
import subprocess
from datetime import datetime
from typing import List, Dict, Optional
try:
    from scripts.user_config import INSTITUTION_DOMAIN
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import INSTITUTION_DOMAIN

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORIA_DIR = os.path.join(BASE_DIR, "memoria")
GMAIL_ALERTS_FILE = os.path.join(MEMORIA_DIR, "gmail_alertas_recientes.json")

# Lista negra de portales de empleo masivos / bots de ofertas
JOB_BOARDS_BLACKLIST = [
    "computrabajo", "laborum", "indeed", "jobleads", "bebee", "trabajo.org",
    "chiletrabajos", "linkedin.com", "bumeran", "getonbrd", "infojobs",
    "opcionempleo", "talent.com", "jooble"
]

# Lista negra de servicios de ocio / videojuegos / marketing masivo
ENTERTAINMENT_SPAM = [
    "twitch.tv", "google play", "steam", "epic games", "playstation",
    "ea.com", "ubisoft", "riotgames", "blizzard", "discord"
]

# Palabras de promociones / marketing a descartar siempre
PROMO_KEYWORDS = [
    "cyber", "promo", "descuento", "oferta", "chollazo", "preventa",
    "65% off", "50% off", "40% off", "liquidación", "rebaja", "cupón",
    "cupon", "black friday", "11.11", "aprovecha", "no te lo pierdas",
    "visto recientemente", "recomendado para ti"
]

def scan_raw_gmail_messages(limit: int = 25) -> List[Dict]:
    """Escanea la bandeja de entrada de Google en Apple Mail."""
    script = f'''
tell application "Mail"
    set resText to ""
    try
        set acc to account "Google"
        set mb to mailbox "INBOX" of acc
        set tot to count of messages of mb
        if tot > {limit} then set tot to {limit}
        repeat with i from 1 to tot
            set m to item i of (messages of mb)
            set s to subject of m
            set snd to sender of m
            set d to (date received of m as text)
            set resText to resText & s & "|||" & snd & "|||" & d & "###MSG###"
        end repeat
    on error err
        set resText to "ERROR|||" & err
    end try
    return resText
end tell
'''
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        if p.returncode != 0:
            return []
        
        items = p.stdout.strip().split("###MSG###")
        messages = []
        for it in items:
            parts = it.split("|||")
            if len(parts) >= 3 and parts[0].strip() != "ERROR":
                s = parts[0].strip()
                snd = parts[1].strip()
                dt = parts[2].strip()
                if s:
                    messages.append({
                        "subject": s,
                        "sender": snd,
                        "date": dt
                    })
        return messages
    except Exception as e:
        print(f"[GMAIL SCAN ERROR] {e}")
        return []

def classify_email(msg: Dict) -> Optional[Dict]:
    """
    Clasifica un correo. Retorna un diccionario con la categoría si es de ALTA SEÑAL,
    o None si debe ser descartado (spam, promos, portales masivos).
    """
    subj = msg.get("subject", "")
    snd = msg.get("sender", "")
    combined = f"{subj} {snd}".lower()

    # 1. Filtro estricto: Portales de empleo masivo
    if any(jb in combined for jb in JOB_BOARDS_BLACKLIST):
        return None

    # 2. Filtro estricto: Videojuegos y ocio
    if any(ent in combined for ent in ENTERTAINMENT_SPAM):
        return None

    # 3. Filtro estricto: Marketing y promociones
    if any(pr in combined for pr in PROMO_KEYWORDS):
        return None

    # 4. CATEGORÍA: Dinero Recibido / Finanzas
    money_triggers = [
        "transferencia recibida", "te transfirieron", "abono realizado",
        "dinero recibido", "recibiste $", "abono en tu cuenta",
        "depósito recibido", "deposito recibido", "comprobante de abono"
    ]
    if any(m in combined for m in money_triggers):
        return {
            "categoria": "DINERO_RECIBIDO",
            "asunto": subj,
            "remitente": snd,
            "fecha": msg.get("date"),
            "mensaje_bot": f"Te transfirieron dinero: {subj}."
        }

    # 5. CATEGORÍA: Paquetes y Envíos (Solo tracking real)
    tracking_triggers = [
        "en camino", "llega hoy", "en reparto", "ha sido despachado",
        "en tránsito", "en transito", "pedido entregado", "arribó al país",
        "en aduana", "disponible para retiro"
    ]
    is_delivery_sender = any(courier in combined for courier in [
        "mercadolibre", "mercado libre", "aliexpress", "chilexpress",
        "starken", "blue express", "correos chile", "dhl", "fedex"
    ])
    if is_delivery_sender and any(tr in combined for tr in tracking_triggers):
        # Limpiar asunto
        clean_subj = subj.replace("Tu paquete", "Tu pedido").strip()
        return {
            "categoria": "ENVIO_PAQUETE",
            "asunto": subj,
            "remitente": snd,
            "fecha": msg.get("date"),
            "mensaje_bot": f"Ojo con tu envío: {subj}."
        }

    # 6. CATEGORÍA: Universidad universidad en Gmail
    if INSTITUTION_DOMAIN and INSTITUTION_DOMAIN in combined:
        return {
            "categoria": "UNIVERSIDAD",
            "asunto": subj,
            "remitente": snd,
            "fecha": msg.get("date"),
            "mensaje_bot": f"Correo universidad: {subj}."
        }

    # 7. CATEGORÍA: Trabajo Directo (Empresa o reclutador individual)
    # Detecta contactos reales de empleo que NO vengan de portales masivos
    job_direct_triggers = [
        "entrevista laboral", "entrevista de trabajo", "proceso de selección",
        "proceso de seleccion", "propuesta laboral", "tu postulación a",
        "tu postulacion a", "vacante de", "interés en tu perfil",
        "interes en tu perfil", "reunión laboral"
    ]
    if any(jd in combined for jd in job_direct_triggers):
        return {
            "categoria": "TRABAJO_DIRECTO",
            "asunto": subj,
            "remitente": snd,
            "fecha": msg.get("date"),
            "mensaje_bot": f"Contacto de trabajo directo de {snd}: {subj}."
        }

    # 8. CATEGORÍA: Mensaje Directo de Persona (no institucional masivo)
    # Si viene de un dominio común (gmail, outlook, yahoo, icloud) o de empresa personal
    # y NO es no-reply, newsletter, bounce, soporte masivo
    spam_prefixes = ["noreply", "no-reply", "newsletter", "mailer", "bounce", "notificaciones", "info@", "contact@"]
    is_automated_sender = any(p in snd.lower() for p in spam_prefixes)

    if not is_automated_sender:
        # Si tiene pinta de correo personal individual
        if any(dom in snd.lower() for dom in ["@gmail.com", "@yahoo.com", "@outlook.com", "@hotmail.com", "@icloud.com"]):
            return {
                "categoria": "MENSAJE_DIRECTO",
                "asunto": subj,
                "remitente": snd,
                "fecha": msg.get("date"),
                "mensaje_bot": f"Te escribió {snd}: {subj}."
            }

    return None

def get_high_signal_gmail_alerts(limit: int = 25) -> List[Dict]:
    """Escanea y retorna únicamente los correos que pasaron el filtro estricto."""
    raw_msgs = scan_raw_gmail_messages(limit)
    high_signal = []
    for m in raw_msgs:
        res = classify_email(m)
        if res:
            high_signal.append(res)
    return high_signal

if __name__ == "__main__":
    print("--- ESCANEANDO GMAIL (el correo personal) CON FILTRO DE ALTA SEÑAL ---")
    alerts = get_high_signal_gmail_alerts(30)
    print(f"Total correos de alta señal encontrados: {len(alerts)}")
    for a in alerts:
        print(f"[{a['categoria']}] {a['remitente']} -> {a['asunto']}")
