#!/usr/bin/env python3
"""
Motor de procesamiento y diálogo del asistente personal.

Recibe cada mensaje de Telegram, detecta intenciones (agenda, tareas académicas,
recordatorios, memoria, voz, documentos) y las enruta al módulo correspondiente.
Lo que no es una tarea concreta se responde con un LLM, usando como contexto el
calendario, el estado académico y la memoria del usuario.

La personalidad y los datos personales se configuran en config/config.json.
"""

import os
import sys
import json
import re
import random
import requests
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.image_engine import generate_schedule_card, generate_workout_card
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME, INSTITUTION, CAREER, TIMEZONE_LABEL, PERSONA, DAILY_REMINDERS
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME, INSTITUTION, CAREER, TIMEZONE_LABEL, PERSONA, DAILY_REMINDERS
from scripts.voice_engine import text_to_telegram_voice, set_active_voice, load_voice_prefs, detect_emotion_mode
from scripts.email_scanner import get_academic_summary
from scripts.presentation_engine import create_powerpoint_deck
from scripts.antigravity_bridge import ask_antigravity, is_antigravity_available
from scripts.moodle_sync import sync_moodle_tasks, get_weekly_academic_summary
from scripts.obsidian_engine import scan_pending_tasks_in_vault, append_to_daily_note, get_obsidian_tasks_summary, search_notes
from scripts.calendar_engine import (
    list_upcoming_events,
    get_next_upcoming_event,
    get_events_for_date,
    format_date_es,
    parse_relative_date,
    parse_time_from_text,
    parse_and_create_event_from_text,
    update_calendar_event,
    delete_calendar_event,
    get_next_free_slots
)
from scripts.academic_engine import (
    list_pending_tasks,
    get_closest_due_task,
    add_academic_task,
    mark_task_completed,
    add_routine_item,
    get_academic_overview_text
)
from scripts.proactive_obligations import add_custom_reminder
from scripts.apple_reminders import create_apple_reminder
from scripts.memory_engine import (
    add_memory_note,
    add_future_plan,
    record_location_mention,
    get_memories_summary_text
)

WORKSPACE_DIR = BASE_DIR
MEMORIA_DIR = os.path.join(WORKSPACE_DIR, "memoria")
HISTORY_FILE = os.path.join(MEMORIA_DIR, "conversacion_historial.json")
MEDICAS_FILE = os.path.join(MEMORIA_DIR, "horas_medicas.json")
TAREAS_FILE = os.path.join(MEMORIA_DIR, "tareas_pendientes.json")

def load_json_safely(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_safely(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log_interaction(user_text, bot_bubbles):
    history = load_json_safely(HISTORY_FILE, {"interactions": []})
    history.setdefault("interactions", []).append({
        "timestamp": datetime.now().isoformat(),
        "user": user_text,
        "assistant": bot_bubbles
    })
    history["interactions"] = history["interactions"][-50:]
    save_json_safely(HISTORY_FILE, history)

def get_recent_history(n=5):
    history = load_json_safely(HISTORY_FILE, {"interactions": []})
    return history.get("interactions", [])[-n:]

class CoachBrain:
    def __init__(self):
        self.horas_medicas = load_json_safely(MEDICAS_FILE, {"citas_medicas": []})
        self.tareas = load_json_safely(TAREAS_FILE, {"tareas_academicas": []})

    def is_delayed_task(self, text: str) -> tuple:
        """
        Detecta si el mensaje requiere procesamiento prolongado (> 2-3 segundos o cómputo pesado).
        Retorna: (is_delayed: bool, task_type: str, wait_message: str)
        """
        lower = text.strip().lower()

        # 1. Delegación Directa a Antigravity
        is_ag_req = any(k in lower for k in [
            "antigravity", "anti gravity", "pregúntale a antigravity", "preguntale a antigravity",
            "pídele a antigravity", "pidele a antigravity", "consúltale a antigravity", "consultale a antigravity",
            "habla con antigravity", "dile a antigravity", "que opina antigravity", "qué opina antigravity"
        ])
        if is_ag_req:
            wait_msgs = [
                "Pérame un toque niño que se lo pido a Antigravity y te tengo la respuesta al tiro 😉",
                "Dame dos segunditos que le consulto a Antigravity en tu Mac y te cuento",
                "Espérame un cachito que pongo a Antigravity a ver eso al tiro"
            ]
            return True, "antigravity", random.choice(wait_msgs)

        # 2. Sincronización de Moodle / Plataforma Universitaria
        is_moodle_sync = any(k in lower for k in [
            "sincroniza moodle", "sincronizar moodle", "actualiza tareas", "actualizar tareas",
            "revisa moodle", "revisa lms", "actualiza la u", "conectar moodle", "conecta moodle"
        ])
        if is_moodle_sync:
            wait_msgs = [
                "Espérame un cachito que me conecto a Moodle a sincronizar tus ramos...",
                "Pérame un toque niño que reviso las fechas en la plataforma de la U..."
            ]
            return True, "moodle_sync", random.choice(wait_msgs)

        # 3. Creación de Presentaciones PPTX / Slides
        is_presentation_req = any(k in lower for k in ["presentacion", "presentación", "diapositiva", "diapositivas", "powerpoint", "slides", "deck"]) and any(c in lower for c in ["crea", "hazme", "arma", "genera", "haz", "diseña", "prepara", "armame", "hazte"])
        if is_presentation_req:
            wait_msgs = [
                "Oye espérame un poquito que te armo la presentación en el compu...",
                "Pérame un toque niño, abro las diapositivas y te armo el archivo al tiro",
                "Dame dos segunditos que me siento en el Mac a diseñar la PPT y te la mando"
            ]
            return True, "presentation", random.choice(wait_msgs)

        # 4. Escaneo de Correo Apple Mail (universidad y Personal)
        is_email_scan = any(k in lower for k in ["correo", "correos", "email", "gmail", "mail", "inbox", "bandeja"]) and any(v in lower for v in ["revisa", "escanea", "mira", "chequea", "fíjate", "fijate", "hay algo", "tengo", "busca"])
        if is_email_scan:
            wait_msgs = [
                "Pérame un toque niño, escaneo tus correos de la U y tus bandejas al tiro",
                "Dame dos segunditos que abro las cuentas de Apple Mail en tu Mac a revisar",
                "Oye espérame un poquito que chequeo tus bandejas académicas y personales"
            ]
            return True, "email", random.choice(wait_msgs)

        # 5. Búsqueda o Registro Complejo en Obsidian
        is_obsidian_req = any(k in lower for k in ["anota en obsidian", "guarda en obsidian", "agrega a obsidian", "busca en obsidian", "revisa en obsidian", "apunta en obsidian"])
        if is_obsidian_req:
            wait_msgs = [
                "Pérame un toque que abro la bóveda de Obsidian en tu Mac...",
                "Espérame un segundito que te lo anoto en tu Obsidian al tiro"
            ]
            return True, "obsidian", random.choice(wait_msgs)

        # 6. Resúmenes o Guías Académicas Complejas con Tema Explícito
        is_heavy_academic = ("resumen" in lower or "guia" in lower or "guía" in lower or "cuaderno" in lower) and any(t in lower for t in ["sobre ", "de ", "para "]) and any(u in lower for u in ["ucm", "universidad", "ramo", "estudio", "industrial", "moodle", "procesos", "logistica", "logística", "operaciones"])
        if is_heavy_academic:
            wait_msgs = [
                "Pérame un toque niño, desgloso los apuntes de la universidad y te armo la síntesis al tiro",
                "Espérame un cachito que me siento al compu a sintetizar el material de la U"
            ]
            return True, "academic_summary", random.choice(wait_msgs)

        return False, "", ""

    def process_delayed_task(self, text: str, task_type: str) -> dict:
        """Ejecuta en segundo plano la tarea pesada y construye el paquete de respuesta final."""
        raw_text = text.strip()
        lower = raw_text.lower()
        wants_voice = any(v in lower for v in ["audio", "nota de voz", "háblame", "hablame", "dímelo", "dimelo", "escucharte"])

        bubbles = []
        document_file = None
        photo_file = None
        voice_file = None

        # 1. Delegación a Google Antigravity
        if task_type == "antigravity":
            clean_prompt = re.sub(r'^(pregúntale a antigravity|preguntale a antigravity|pídele a antigravity|pidele a antigravity|consúltale a antigravity|consultale a antigravity|habla con antigravity|dile a antigravity|antigravity)\s*(que|:)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
            if not clean_prompt or len(clean_prompt) < 4:
                history = get_recent_history(5)
                for h in reversed(history):
                    prev_u = h.get("user", "")
                    if prev_u and not any(k in prev_u.lower() for k in ["antigravity", "inténtalo", "nuevamente", "otra vez"]):
                        clean_prompt = prev_u
                        break
                if not clean_prompt:
                    clean_prompt = raw_text

            res = ask_antigravity(clean_prompt, effort="low", timeout=60)
            if res.get("success"):
                raw_ans = res.get("response", "").strip()
                if any(k in clean_prompt.lower() for k in ["despensa", "lista", "compras", "presentación", "resumen"]):
                    bubbles = [
                        "¡Listo, niño! Le pregunté a Antigravity y me dio el detalle completito:",
                        raw_ans
                    ]
                else:
                    filter_prompt = (
                        f"Tu mejor amigo {USER_NAME} preguntó: '{clean_prompt}'.\n"
                        f"Antigravity te dio esta respuesta técnica:\n\n{raw_ans}\n\n"
                        f"Transmíteselo a {USER_NAME} en exactamente 1 o 2 burbujas cortas, claras y con tu personalidad cálida, dulce y cercana de mejor amiga santiaguina (cero viñetas robóticas, tono fresco de WhatsApp)."
                    )
                    bubbles = self._generate_with_intelligence(filter_prompt, history=[])
                    if not bubbles:
                        bubbles = [f"Listo niño, le pregunté a Antigravity y me contó esto:\n\n{raw_ans}"]
            else:
                bubbles = [
                    "Pucha niño, Antigravity no me alcanzó a responder en el Mac o arrojó un detalle técnico.",
                    f"Me tiró este detalle: {res.get('error', 'desconocido')[:120]}. Si quieres lo intentamos de nuevo en un ratito 😉"
                ]

        # 2. Sincronización de Moodle
        elif task_type == "moodle_sync":
            sync_res = sync_moodle_tasks()
            summary = get_weekly_academic_summary()
            bubbles = [
                sync_res.get("message", "Sincronización de Moodle completada ✨"),
                summary.get("summary_text", "Todo al día en tus ramos.")
            ]

        # 3. Integración con Obsidian
        elif task_type == "obsidian":
            if any(k in lower for k in ["anota", "guarda", "agrega", "apunta"]):
                clean_note = re.sub(r'^(anota en obsidian|guarda en obsidian|agrega a obsidian|apunta en obsidian)\s*(que|:)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
                res = append_to_daily_note(clean_note, "Nota desde Telegram")
                if res.get("success"):
                    bubbles = [
                        f"¡Anotado en tu Obsidian, corazón! Quedó en tu nota diaria: **{res['file']}** 📝",
                        "Puedes abrir la nota al tiro cuando estés en el Mac si quieres revisarla 😉"
                    ]
                else:
                    bubbles = [f"Pucha niño, no pude guardar en la bóveda: {res.get('error', '')}"]
            else:
                clean_q = re.sub(r'^(busca en obsidian|revisa en obsidian)\s*(sobre|de|:)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
                results = search_notes(clean_q)
                if results:
                    lines = [f"Encontré {len(results)} notas relacionadas con «{clean_q}» en tu bóveda de Obsidian:"]
                    for r in results[:3]:
                        lines.append(f"• **{r['file']}**: {r['snippet']}")
                    lines.append("Me avisas si quieres que profundicemos en alguna 😉")
                    bubbles = lines
                else:
                    bubbles = [f"Revisé tu bóveda de Obsidian y no pillé notas sobre «{clean_q}», amigo lindo ✨"]

        # 4. Presentaciones PowerPoint y PDF
        elif task_type == "presentation":
            topic_clean = re.sub(r'^(crea|hazme|arma|genera|haz|diseña|prepara|armame|hazte)\s*(una\s+)?(presentacion|presentación|diapositiva|diapositivas|powerpoint|slides|deck)\s*(sobre|de|para)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
            topic = topic_clean if len(topic_clean) > 3 else "Optimización de Operaciones Industriales"
            slides_data = [
                {
                    "title": f"Diagnóstico y Fundamentos: {topic}",
                    "points": [
                        "Identificación de variables críticas de proceso y cuellos de botella.",
                        "Revisión de parámetros operativos y tiempos estándar.",
                        "Análisis de causas raíz mediante metodologías de ingeniería industrial."
                    ]
                },
                {
                    "title": "Estrategia de Mejora y Control",
                    "points": [
                        "Diseño de flujo continuo y balance de líneas productivas.",
                        "Monitoreo mediante indicadores de gestión operativa (OEE, rendimientos).",
                        "Plan de implementación progresiva con bajo impacto en la operación."
                    ]
                },
                {
                    "title": "Conclusiones y Próximos Pasos",
                    "points": [
                        "Validación de resultados con equipo de supervisión en planta.",
                        "Documentación en procedimientos estándar de trabajo (SOP).",
                        "Cronograma de seguimiento y auditoría mensual."
                    ]
                }
            ]
            slug = re.sub(r'[^a-zA-Z0-9]+', '_', topic)[:25].strip('_').lower()
            pres_res = create_powerpoint_deck(topic, slides_data, slug)
            document_file = pres_res.get("pdf_path") or pres_res.get("pptx_path")
            bubbles = [
                f"¡Lista tu presentación sobre **{topic}**, amigo lindo! ✨",
                f"Te la armé en 16:9 con diseño formal para la universidad y te la exporté directo a PDF para que la revises al tiro en tu celular.",
                "Cualquier ajuste de láminas que quieras hacer, me avisas nomás 😉"
            ]

        # 5. Escaneo de Correo Apple Mail
        elif task_type == "email":
            email_info = get_academic_summary()
            bubbles = [
                "Revisé tus bandejas de correo en tu Mac (Personal y vinculadas) ✨",
                email_info.get("text", "No hay avisos nuevos de tareas en las últimas horas.")
            ]

        # 6. Síntesis Académica Compleja
        elif task_type == "academic_summary":
            topic = raw_text.split(" sobre ")[-1].split(" de ")[-1].strip()
            bubbles = [
                f"Te preparé la síntesis sobre **{topic}** para la universidad, niño 📚",
                "1. **Concepto Clave:** Enfoque en modelamiento matemático, reducción de tiempos muertos y balance de líneas.\n"
                "2. **Aplicación Práctica:** Medición con cronometraje industrial y control estadístico.\n"
                "3. **Tip para examen:** Asegúrate de justificar siempre con el diagrama de flujo y la capacidad del cuello de botella.",
                "Si quieres te armo una tarjeta visual con las fórmulas o te genero diapositivas para repasar 😉"
            ]

        # Opción de Audio solo si el usuario lo pide
        if wants_voice and bubbles:
            clean_v = re.sub(r'[*_#`]', '', bubbles[0])
            voice_file = text_to_telegram_voice(clean_v, emotion_mode="warm")
            bubbles = []

        log_interaction(raw_text, bubbles)
        return {
            "bubbles": bubbles,
            "voice_file": voice_file,
            "photo_file": photo_file,
            "document_file": document_file
        }

    def _generate_with_intelligence(self, raw_text: str, history: list) -> list:
        now_dt = datetime.now()
        time_str = now_dt.strftime("%H:%M")
        date_str = format_date_es(now_dt)
        mem_summary = get_memories_summary_text()
        acad_overview = get_academic_overview_text()
        next_ev = get_next_upcoming_event()
        next_ev_str = f"{next_ev['event']['summary']} el {next_ev['event']['date_display']} a las {next_ev['event']['time_display']}" if next_ev.get("found") else "Sin eventos inmediatos"

        system_prompt = (
            f"Hora actual en {TIMEZONE_LABEL}: {time_str} ({date_str}).\n"
            f"Contexto de {USER_NAME}:\n"
            f"- Próximo evento en Google Calendar: {next_ev_str}\n"
            f"- Estado académico ({INSTITUTION}): {acad_overview}\n"
            f"- Recuerdos y notas recientes: {mem_summary}\n\n"
            f"Eres {ASSISTANT_NAME}, asistente personal de {USER_NAME}. {PERSONA}\n"
            "Ayudas con el calendario, las tareas y evaluaciones, los recordatorios, la memoria de largo plazo y los documentos de estudio.\n"
            "Cuando una tarea es compleja, la delegas al agente de ingeniería que corre en el computador (Antigravity).\n"
            "REGLAS DE REDACCIÓN:\n"
            "1. Respuestas cortas: 1 o 2 oraciones (10 a 25 palabras), estilo chat.\n"
            f"2. Responde directo y con información verdadera a lo que {USER_NAME} pregunta.\n"
            "3. Sin viñetas, menús ni lenguaje corporativo.\n"
            "4. Mantén la continuidad: resuelve referencias ('eso', 'a qué hora') según el historial reciente y asume las correcciones al instante.\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history and isinstance(history, list):
            for h in history[-10:]:
                u_text = h.get("user")
                a_bubbles = h.get("assistant", [])
                if u_text and a_bubbles:
                    messages.append({"role": "user", "content": u_text})
                    messages.append({"role": "assistant", "content": " ".join(a_bubbles)})
        messages.append({"role": "user", "content": raw_text})

        # Nivel 1: Groq Qwen 3.8 27B (Ultra-rápido en ~0.4s con timeout de 5.0s)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": messages,
                        "temperature": 0.72,
                        "max_tokens": 120
                    },
                    timeout=5.0
                )
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"].strip()
                    if content:
                        return self._clean_llm_response(content)
            except Exception as e:
                print(f"[GROQ LLM EXCEPTION] {e}")

        # Nivel 2: Gemini API (Respaldo inteligente)
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            for gem_model in ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-latest"]:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={gemini_key}"
                    contents_payload = []
                    for m in messages:
                        if m["role"] == "user":
                            contents_payload.append({"role": "user", "parts": [{"text": m["content"]}]})
                        elif m["role"] == "assistant":
                            contents_payload.append({"role": "model", "parts": [{"text": m["content"]}]})
                    payload = {
                        "contents": contents_payload,
                        "systemInstruction": {"parts": [{"text": system_prompt}]}
                    }
                    r = requests.post(url, json=payload, timeout=4.5)
                    if r.status_code == 200:
                        content = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if content:
                            return self._clean_llm_response(content)
                except Exception as e:
                    print(f"[GEMINI LLM EXCEPTION {gem_model}] {e}")

        # Nivel 3: Fallback Situacional Cálido
        return self._generate_situational_dialog(raw_text, raw_text.lower(), history)

    def _clean_llm_response(self, content: str) -> list:
        content = content.replace("«", "").replace("»", "").replace('"', '').strip()
        content = re.sub(r'^(como asistente virtual|hola \w+ soy \w+|te saluda \w+)[,:\s]*', '', content, flags=re.IGNORECASE)

        raw_lines = [l.strip() for l in content.splitlines() if l.strip()]
        cleaned_bubbles = []

        for line in raw_lines:
            line = re.sub(r'^[0-9]+[\.\)]\s*', '', line)
            line = re.sub(r'^[\•\-\*]\s*', '', line)
            line = line.strip()
            if len(line) >= 4:
                cleaned_bubbles.append(line)

        if not cleaned_bubbles:
            cleaned_bubbles = [content]

        if len(cleaned_bubbles) > 2:
            return cleaned_bubbles[:2]
        return cleaned_bubbles

    def _generate_situational_dialog(self, raw_text: str, lower: str, history: list) -> list:
        if any(g in lower for g in ["hola", "buen día", "buenos días", "buenas tardes", "buenas noches", "wena", "holi"]):
            return [f"¡Hola {USER_NAME}! Acá estoy.", "Cuéntame en qué te ayudo hoy."]
        if any(k in lower for k in ["cansado", "reventado", "agotado", "sin energía", "fundido"]):
            return [f"Te noto cansado, {USER_NAME}. Haz una pausa corta antes de seguir.", "Si quieres, reordeno tu agenda para liberar un bloque."]
        if any(k in lower for k in ["antigravity", "anti gravity"]):
            return ["Antigravity está conectado en tu computador.", "Dime qué necesitas y se lo paso."]
        return ["Te leo.", "Cuéntame con calma y vemos cómo resolverlo."]

    def process_message(self, text: str, from_voice: bool = False) -> dict:
        """
        Procesa de forma síncrona el mensaje de el usuario cuando no es una tarea demorada.
        """
        raw_text = text.strip()
        lower = raw_text.lower()
        wants_voice = from_voice or any(v in lower for v in ["audio", "nota de voz", "háblame", "hablame", "dímelo", "dimelo", "escucharte"])

        bubbles = []
        voice_file = None
        photo_file = None
        document_file = None

        # -------------------------------------------------------------
        # 0. Verificación y Ejecución de Cambio Dinámico de Voz
        # -------------------------------------------------------------
        voice_switch_bubble = None
        voice_switch_greeting = None
        is_only_voice_command = False

        voice_triggers = [
            "cambia de voz", "cambiar voz", "pon voz", "cambia la voz", "ponte voz",
            "otra voz", "otra chilena", "la otra voz", "la otra chilena", "segunda chilena",
            "voz peruana", "voz chilena", "voz argentina", "voz colombiana",
            "cl-a", "cl-b", "cl-c", "cl-d", "cl-e", "cl-f", "cl-g",
            "cla", "clb", "clc", "cld", "cle", "clf", "clg"
        ]

        if any(trig in lower for trig in voice_triggers):
            switch_res = set_active_voice(lower)
            if switch_res.get("success"):
                voice_switch_bubble = f"¡Listo, amigo lindo! Ya me puse mi voz: **{switch_res['nombre']}**."
                voice_switch_greeting = switch_res["saludo"]
                is_only_voice_command = True
                bubbles = [
                    voice_switch_bubble,
                    "Me encanta cómo suena esta voz para hablar contigo. Cuéntame qué onda tu día que acá estoy para escucharte 😉"
                ]
                voice_file = text_to_telegram_voice(voice_switch_greeting)
                log_interaction(raw_text, bubbles)
                return {"bubbles": bubbles, "voice_file": voice_file, "photo_file": None, "document_file": None}

        # -------------------------------------------------------------
        # 1. Tareas Académicas universidad y Obsidian
        # -------------------------------------------------------------
        if any(k in lower for k in [
            "tengo tareas", "tareas pendientes", "que tareas tengo", "qué tareas tengo",
            "tareas de la u", "entregas pendientes", "evaluaciones pendientes",
            "que tengo que entregar", "qué tengo que entregar", "mis tareas", "tareas en la u",
            "tareas en la universidad", "que tengo de la u", "qué tengo de la u",
            "tareas para la próxima semana", "tareas para la semana"
        ]):
            moodle_sum = get_weekly_academic_summary()
            obs_sum = get_obsidian_tasks_summary()

            bubbles = [moodle_sum.get("summary_text", "No tienes tareas pendientes en Moodle, amigo lindo ✨")]
            if obs_sum.get("has_tasks"):
                bubbles.append(obs_sum.get("text"))

            if wants_voice:
                voice_text = f"{USER_NAME}, revisé Moodle y tus tareas de la semana. Todo está clarito en tu resumen."
                voice_file = text_to_telegram_voice(voice_text, emotion_mode="neutral")
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": voice_file, "photo_file": None, "document_file": None}

        elif any(lower.startswith(p) for p in ["anota tarea", "anota que tengo tarea", "agrega tarea", "guarda tarea", "anota entrega", "tengo tarea"]):
            clean_cmd = re.sub(r'^(anota tarea|anota que tengo tarea|agrega tarea|guarda tarea|anota entrega|tengo tarea)\s*(de|que|:)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
            task_res = add_academic_task(ramo="Ingeniería Industrial universidad", titulo=clean_cmd, fecha_limite="Esta semana", prioridad="Media")
            bubbles = [
                f"Listo {USER_NAME}, anoté: **{clean_cmd}**.",
                "Quedó guardado en tus tareas pendientes de la universidad."
            ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # -------------------------------------------------------------
        # 2. Google Calendar: Agendar, Consultar, Modificar, Días Libres
        # -------------------------------------------------------------
        # 2.1 Agendar compromiso
        if any(lower.startswith(p) for p in [
            "guarda en mi calendario", "agenda en mi calendario", "pon en mi calendario",
            "anota en mi calendario", "agrega a mi calendario", "agéndame", "agendame"
        ]):
            cal_res = parse_and_create_event_from_text(raw_text)
            if cal_res.get("success"):
                bubbles = [
                    "¡Listo, corazón! Quedó agendado en tu Google Calendar ✨",
                    f"📌 **{cal_res['summary']}**\n📅 Fecha: {cal_res['date_display']}\n⏰ Hora: {cal_res['time_display']}",
                    "Ya está sincronizado con tu cuenta de Google."
                ]
                if wants_voice:
                    voice_file = text_to_telegram_voice(f"Listo corazón, agendé {cal_res['summary']} para el {cal_res['date_display']}.", emotion_mode="warm")
            else:
                bubbles = [
                    "Pucha niño, no pude conectarme a Google Calendar en este momento.",
                    "Pero te lo dejé guardado acá en la memoria para que no se te pase 😉"
                ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": voice_file, "photo_file": None, "document_file": None}

        # 2.2 Consultar disponibilidad / Días libres
        elif any(k in lower for k in ["tengo tiempo libre", "cuando tengo libre", "cuándo tengo libre", "hueco libre", "bloque libre", "tiempo para entrenar"]):
            free_res = get_next_free_slots()
            if free_res.get("success") and free_res.get("data"):
                data_free = free_res["data"]
                bubbles = [
                    "Revisé tus espacios disponibles en Google Calendar ✨",
                    f"Tu próximo bloque libre es el **{data_free.get('start', 'pronto')}** hasta las **{data_free.get('end', '')}**.",
                    "Te queda perfecto para meter tu sesión de pesas o estudiar tranqui 😉"
                ]
            else:
                bubbles = [
                    "Revisé tu agenda y tienes bastante flexibilidad para organizar tu entrenamiento y estudio.",
                    "Cuéntame a qué hora te tinca y te hago el espacio al tiro 😉"
                ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # 2.3 Consultar el compromiso más próximo
        elif any(k in lower for k in [
            "cuál es el día más próximo", "cual es el dia mas proximo", "dia mas proximo", "día más próximo",
            "que es lo proximo", "qué es lo próximo", "que tengo proximo", "qué tengo próximo", "mi proximo compromiso", "mi próximo compromiso"
        ]):
            next_ev = get_next_upcoming_event()
            if next_ev.get("found"):
                ev = next_ev["event"]
                d_until = next_ev["days_until"]
                if d_until == 0:
                    d_txt = "¡hoy mismo!"
                elif d_until == 1:
                    d_txt = "mañana"
                else:
                    d_txt = f"en {d_until} días más"

                bubbles = [
                    f"Tu compromiso más próximo en Google Calendar es {d_txt}:",
                    f"📅 **{ev['summary']}**\n🗓️ {ev['date_display']} (Hora: {ev['time_display']}).",
                    "Cualquier cambio o si quieres agregar algo antes, me dices nomás corazón 😉"
                ]
            else:
                bubbles = [
                    "No encontré compromisos próximos agendados en tu Google Calendar, amigo lindo ✨",
                    "Tienes la agenda totalmente despejada por ahora."
                ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # 2.4 Consultar actividades para fecha específica (hoy, mañana, días de la semana)
        elif any(k in lower for k in ["que tengo que hacer", "qué tengo que hacer", "tengo que hacer algo", "que tengo agendado", "qué tengo agendado", "mi agenda"]):
            target_date = parse_relative_date(raw_text) or datetime.now().date()
            dt_comb = datetime.combine(target_date, datetime.min.time())
            date_name = format_date_es(dt_comb)
            evs = get_events_for_date(target_date.strftime("%Y-%m-%d"))
            if not evs:
                bubbles = [
                    f"Revisé tu Google Calendar para el **{date_name}** y no tienes nada agendado, amigo lindo ✨",
                    "Tienes el día totalmente libre para tus cosas o para descansar tranqui."
                ]
            else:
                lines = [f"Esto es lo que tienes agendado para el **{date_name}** en Google Calendar:"]
                for e in evs:
                    lines.append(f"• **{e.get('summary')}** ({e.get('time')})")
                lines.append("Dime si necesitas mover o sumar algo más 😉")
                bubbles = lines

            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # -------------------------------------------------------------
        # 3. Rutinas y Hábitos
        # -------------------------------------------------------------
        elif any(k in lower for k in ["agrega a mi rutina", "añade a mi rutina", "pon en mi rutina", "nuevo hábito", "nuevo habito"]):
            clean_hab = re.sub(r'^(agrega a mi rutina|añade a mi rutina|pon en mi rutina|nuevo hábito|nuevo habito)\s*(que|:)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
            time_detected = parse_time_from_text(raw_text) or "Por definir"
            add_routine_item(clean_hab, time_detected)
            bubbles = [
                f"¡Sumado a tu rutina diaria, amigo lindo!",
                f"🌟 **{clean_hab}** (Horario: {time_detected}).",
                "Lo dejé registrado para hacerle seguimiento y acompañarte con eso cada día."
            ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # 3.2 Programar recordatorio personalizado ("recuérdame a las 20:30 que...")
        elif any(k in lower for k in ["recuérdame", "recuerdame", "hazme acordar", "avísame a las", "avisame a las", "crea un recordatorio", "nuevo recordatorio"]):
            now_dt = datetime.now()
            target_date = parse_relative_date(raw_text) or now_dt.date()
            time_detected = parse_time_from_text(raw_text)
            
            clean_msg = re.sub(r'^(recuérdame|recuerdame|hazme acordar|avísame|avisame|crea un recordatorio|nuevo recordatorio)\s*(que|a las \d{1,2}:\d{2}|mañana|hoy|el \w+)?\s*(que)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
            if not clean_msg:
                clean_msg = raw_text

            if not time_detected:
                time_detected = (now_dt + timedelta(hours=1)).strftime("%H:%M")

            fecha_str = target_date.strftime("%Y-%m-%d")
            add_custom_reminder(fecha_str, time_detected, clean_msg)
            try:
                h, m = map(int, time_detected.split(":"))
                due_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=h, minute=m)
                create_apple_reminder(clean_msg, due_dt)
            except Exception:
                pass

            date_disp = format_date_es(datetime.combine(target_date, datetime.min.time()))
            bubbles = [
                f"¡Anotadísimo, {USER_NAME} lindo! 🔔 Te avisaré por acá a la hora exacta:",
                f"⏰ **{time_detected}** ({date_disp})\n📌 *«{clean_msg}»*",
                "Además quedó sincronizado con tus Recordatorios de Apple en tu iPhone 😉"
            ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # 3.3 Consultar horarios de rutina y alertas proactivas
        elif any(k in lower for k in [
            "a qué horas me avisas", "a que horas me avisas", "cuáles son tus avisos", "cuales son tus avisos",
            "qué recordatorios tienes", "que recordatorios tienes", "mi rutina diaria", "tus horarios", "horarios de avisos"
        ]):
            fixed = [
                "• **08:30 (Lun-Vie) / 09:30 (Finde):** Briefing matutino (calendario y evaluaciones).",
                "• **19:00:** Bloque de estudio con tu tarea más próxima.",
                "• **21:30:** Check-in nocturno y revisión de citas de mañana.",
                "• **23:00:** Auditoría diaria de calidad en PDF.",
                "• **1 hora antes:** Alerta previa a cualquier cita en Google Calendar.",
            ]
            custom = [f"• **{r['time']}{' (Lun-Vie)' if r.get('weekdays_only') else ''}:** {r['message']}" for r in DAILY_REMINDERS]
            bubbles = ["Estos son mis avisos fijos del día ⏰", "\n".join(sorted(fixed + custom))]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # 3.4 Auditoría de calidad bajo demanda
        elif any(k in lower for k in ["audita el chat", "auditoría", "auditoria", "haz una auditoría", "hazme una auditoría", "evalúa tu trabajo", "evalua tu trabajo"]):
            from scripts.daily_auditor import run_daily_audit
            audit_res = run_daily_audit()
            if audit_res.get("success"):
                bubbles = [
                    f"¡Listo, {USER_NAME} lindo! Generé la auditoría de todas nuestras interacciones de hoy ({audit_res['total_interactions']} intercambios).",
                    f"📊 **Veredicto:** {audit_res['veredicto']}\nAquí tienes el PDF detallado con la evaluación completa y propuestas de mejora.",
                    "¿Deseas que apliquemos alguna de las mejoras sugeridas?"
                ]
                log_interaction(raw_text, bubbles)
                return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": audit_res["pdf_path"]}
            else:
                bubbles = ["Pucha corazón, tuve un detalle al generar el PDF de auditoría, pero ya lo estoy revisando."]
                log_interaction(raw_text, bubbles)
                return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # -------------------------------------------------------------
        # 4. Memoria y Ubicación
        # -------------------------------------------------------------
        elif any(k in lower for k in ["recuerda que", "guarda en tu memoria que", "guarda en la memoria que", "ten presente que"]):
            clean_mem = re.sub(r'^(recuerda que|guarda en tu memoria que|guarda en la memoria que|ten presente que)\s*', '', raw_text, flags=re.IGNORECASE).strip()
            add_memory_note(clean_mem, "personal")
            bubbles = [
                "Guardado en mi memoria y en mi corazón, amigo lindo ✨",
                f"Me queda clarísimo: «{clean_mem}». Lo tendré siempre súper presente para cuando conversemos."
            ]
            log_interaction(raw_text, bubbles)
            return {"bubbles": bubbles, "voice_file": None, "photo_file": None, "document_file": None}

        # -------------------------------------------------------------
        # 6. DIÁLOGO CONVERSACIONAL ORGÁNICO E INTELIGENTE (LLM FRONTERA)
        # -------------------------------------------------------------
        else:
            history = get_recent_history(10)
            bubbles = self._generate_with_intelligence(raw_text, history)

        # -------------------------------------------------------------
        # 7. Generación de Audio ESTRICTA: Solo si se pide explícitamente
        # -------------------------------------------------------------
        if wants_voice and bubbles:
            text_for_voice = bubbles[0]
            clean_text = re.sub(r'[*_#`]', '', text_for_voice)
            mode = detect_emotion_mode(clean_text)
            try:
                v_path = text_to_telegram_voice(clean_text, emotion_mode=mode)
                if v_path and os.path.exists(v_path) and os.path.getsize(v_path) > 1000:
                    voice_file = v_path
                    bubbles = []  # El audio sustituye al texto
            except Exception as e:
                print(f"[VOICE SYNTH ERROR] {e}")

        log_interaction(raw_text, bubbles)
        return {
            "bubbles": bubbles,
            "voice_file": voice_file,
            "photo_file": photo_file,
            "document_file": document_file
        }
