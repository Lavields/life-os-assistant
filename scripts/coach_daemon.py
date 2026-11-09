#!/usr/bin/env python3
"""
Daemon del asistente personal en Telegram.

- Recibe texto, notas de voz, fotos y documentos desde un único chat autorizado.
- Delega las consultas complejas al agente Antigravity que corre en el computador,
  con confirmación inmediata y avisos de progreso mientras trabaja.
- Responde con burbujas cortas, notas de voz (.ogg Opus), tarjetas visuales y PDFs.
- Hilo proactivo: briefing matutino, sincronización académica, alertas de Google
  Calendar, recordatorios configurables y auditoría diaria.
"""

import os
import sys
import time
import json
import fcntl
import random
import threading
import requests
from datetime import datetime

# Desactivar buffer de salida
sys.stdout.reconfigure(line_buffering=True)

# Mecanismo de Bloqueo Singleton (Garantiza que NUNCA corran 2 instancias simultáneas)
LOCK_FILE = "/tmp/coach_daemon_singleton.lock"
try:
    _lock_fd = open(LOCK_FILE, "w")
    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
except (IOError, BlockingIOError):
    print(f"[SECURITY] Ya existe una instancia de coach_daemon activa con PID en ejecución. Saliendo para evitar duplicados.")
    sys.exit(0)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.coach_brain import CoachBrain, log_interaction, get_recent_history
from scripts.antigravity_bridge import ask_antigravity
from scripts.academic_scanner import run_academic_sync
from scripts.document_engine import build_notebooklm_bundle
from scripts.image_engine import generate_workout_card
from scripts.voice_engine import text_to_telegram_voice, transcribe_telegram_voice
from scripts.daily_auditor import run_daily_audit
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME, CAREER, DAILY_REMINDERS
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME, CAREER, DAILY_REMINDERS
from scripts.proactive_obligations import (
    get_morning_briefing,
    get_evening_briefing,
    get_study_focus_bubbles,
    get_calendar_pre_alert,
    check_and_pop_custom_reminders,
    add_custom_reminder,
    has_alert_been_sent,
    save_sent_alert,
    in_time_window
)

# Cargar variables de entorno desde .env
ENV_FILE = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

from scripts.env_loader import install_log_redaction, is_safe_outgoing_file, release_delivered_document
install_log_redaction()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))  # obligatorio: solo este chat puede usar el bot
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

ACK_PHRASES = [
    "Dame un momento, me pongo en ello ✨",
    "Voy a revisar eso enseguida.",
    "Estoy trabajando en ello, dame un ratito...",
    "Entendido, me pongo manos a la obra.",
]

class TelegramCoachDaemon:
    def __init__(self):
        self.brain = CoachBrain()
        self.last_update_id = 0
        self.is_running = True
        self.sent_alerts_today = set()
        self.pending_tasks = {}
        self.current_date = datetime.now().date()

    def send_action(self, chat_id: int, action: str = "typing"):
        try:
            requests.post(f"{BASE_URL}/sendChatAction", json={"chat_id": chat_id, "action": action}, timeout=5)
        except Exception as e:
            print(f"[ACTION ERROR] {e}")

    def send_message(self, chat_id: int, text: str):
        try:
            res = requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
            return res.json()
        except Exception as e:
            print(f"[MSG ERROR] {e}")
            return None

    def send_voice(self, chat_id: int, voice_path: str):
        try:
            self.send_action(chat_id, "record_voice")
            with open(voice_path, "rb") as f:
                res = requests.post(f"{BASE_URL}/sendVoice", data={"chat_id": chat_id}, files={"voice": f}, timeout=25)
            return res.json()
        except Exception as e:
            print(f"[VOICE ERROR] {e}")
            return None

    def send_photo(self, chat_id: int, photo_path: str, caption: str = None):
        try:
            self.send_action(chat_id, "upload_photo")
            with open(photo_path, "rb") as f:
                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption
                res = requests.post(f"{BASE_URL}/sendPhoto", data=data, files={"photo": f}, timeout=25)
            return res.json()
        except Exception as e:
            print(f"[PHOTO ERROR] {e}")
            return None

    def send_document(self, chat_id: int, doc_path: str, caption: str = None):
        try:
            self.send_action(chat_id, "upload_document")
            with open(doc_path, "rb") as f:
                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption
                res = requests.post(f"{BASE_URL}/sendDocument", data=data, files={"document": f}, timeout=35)
            return res.json()
        except Exception as e:
            print(f"[DOC ERROR] {e}")
            return None

    def download_telegram_file(self, file_id: str, dest_path: str) -> bool:
        try:
            info_res = requests.get(f"{BASE_URL}/getFile?file_id={file_id}", timeout=10).json()
            if not info_res.get("ok"):
                return False
            file_path = info_res["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            r = requests.get(download_url, stream=True, timeout=60)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"[DOWNLOAD ERROR] {e}")
            return False

    def deliver_response_package(self, chat_id: int, package: dict):
        """Envía ráfagas multi-burbuja naturales con efecto 'escribiendo' y pausa de 5 segundos entre mensajes."""
        bubbles = package.get("bubbles", [])
        voice_file = package.get("voice_file")
        photo_file = package.get("photo_file")
        document_file = package.get("document_file")

        # Regla de Oro: Si hay nota de voz, el audio sustituye al texto (cero redundancia)
        if voice_file and os.path.exists(voice_file) and os.path.getsize(voice_file) > 1000:
            bubbles = []

        for i, bubble in enumerate(bubbles):
            if i > 0:
                # Si hay más de un mensaje, esperar 5 segundos simulando escritura humana
                for _ in range(5):
                    self.send_action(chat_id, "typing")
                    time.sleep(1.0)
            else:
                self.send_action(chat_id, "typing")
                time.sleep(1.2)
            self.send_message(chat_id, bubble)

        if photo_file and os.path.exists(photo_file):
            time.sleep(1.5)
            self.send_photo(chat_id, photo_file)
            if "/tmp" in photo_file or "/var/" in photo_file:
                try:
                    os.remove(photo_file)
                except Exception:
                    pass

        if voice_file and os.path.exists(voice_file):
            time.sleep(1.5)
            self.send_voice(chat_id, voice_file)
            try:
                os.remove(voice_file)
            except Exception:
                pass

        if document_file and os.path.exists(document_file):
            time.sleep(1.5)
            sent = self.send_document(chat_id, document_file)
            # Solo se libera si Telegram confirmó la entrega: si falla, el PDF se conserva
            if isinstance(sent, dict) and sent.get("ok"):
                try:
                    release_delivered_document(document_file)
                except OSError as e:
                    print(f"[DOC CLEANUP ERROR] {e}")

    def _build_contextual_prompt(self, current_text: str, n_history: int = 8) -> str:
        """
        Construye un prompt enriquecido con el historial reciente de conversación
        para que Antigravity mantenga el hilo continuo y no sufra amnesia conversacional.
        """
        try:
            recent = get_recent_history(n_history)
            if not recent:
                return current_text

            lines = ["[HISTORIAL RECIENTE DE LA CONVERSACIÓN CON USUARIO]:"]
            for turn in recent:
                u = turn.get("user", "").strip()
                a_bubbles = turn.get("assistant", [])
                a = " ".join(a_bubbles).strip() if isinstance(a_bubbles, list) else str(a_bubbles).strip()
                if u:
                    lines.append(f"- {USER_NAME}: {u}")
                if a:
                    lines.append(f"- {ASSISTANT_NAME}: {a}")
            lines.append("[FIN HISTORIAL]")
            lines.append(f"\n[MENSAJE ACTUAL DE USUARIO]:\n{current_text}")
            lines.append(f"\n(Directiva: Responde al mensaje actual de {USER_NAME} manteniendo coherencia total con el historial de arriba. Resuelve referencias relativas como 'eso', 'él', 'con quién', 'a qué hora', 'lo hiciste' según lo conversado).")
            return "\n".join(lines)
        except Exception as e:
            print(f"[CONTEXT BUILD ERROR] {e}")
            return current_text

    def _process_with_antigravity_async(self, chat_id: int, text: str, is_from_voice: bool = False):
        """
        Worker asíncrono central:
        - Delega todo a Antigravity (agy CLI).
        - CERO mensajes automáticos inmediatos tipo bot.
        - Solo si Antigravity lleva 5 minutos sin contestar, envía un mensaje orgánico de espera.
        """
        stop_event = threading.Event()

        def heartbeat_worker():
            # Intervalos: solo avisa a partir de los 5 minutos (300s) si la tarea es muy pesada
            heartbeats = [
                (300, "Me pongo a hacer eso, me está tomando algo de tiempo pero ya voy."),
                (600, "Sigo trabajando en esto, me falta poco."),
                (900, "Ya casi lo tengo listo, un momento más.")
            ]
            start_t = time.time()
            for delay, msg in heartbeats:
                target_wait = delay - (time.time() - start_t)
                if target_wait > 0:
                    if stop_event.wait(timeout=target_wait):
                        return
                if stop_event.is_set():
                    return
                self.send_action(chat_id, "typing")
                self.send_message(chat_id, msg)

        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        hb_thread.start()

        try:
            prompt_with_context = self._build_contextual_prompt(text, n_history=8)
            print(f"[ANTIGRAVITY ASYNC START] '{text}'")
            res = ask_antigravity(prompt_with_context, effort="medium", timeout=1200)
            stop_event.set()

            if res.get("success"):
                package = res.get("package", {})
                bubbles = package.get("bubbles", [])
                wants_voice = package.get("wants_voice", False) or is_from_voice
                voice_text = package.get("voice_text", "")
                photo_path = package.get("photo_path")
                doc_path = package.get("document_path")
                for label, candidate in (("foto", photo_path), ("documento", doc_path)):
                    if candidate and not is_safe_outgoing_file(candidate):
                        print(f"[SEGURIDAD] Archivo saliente bloqueado ({label})")
                if not is_safe_outgoing_file(photo_path):
                    photo_path = None
                if not is_safe_outgoing_file(doc_path):
                    doc_path = None

                voice_file = None
                if wants_voice:
                    speak_text = voice_text if (voice_text and voice_text.strip()) else " ".join(bubbles)
                    if speak_text and speak_text.strip():
                        try:
                            # En audio no hay límite de palabras: se sintetiza completo en un solo audio
                            voice_file = text_to_telegram_voice(speak_text.strip(), emotion_mode="neutral")
                        except Exception as ve:
                            print(f"[VOICE SYNTH ERROR] {ve}")

                self.deliver_response_package(chat_id, {
                    "bubbles": bubbles,
                    "voice_file": voice_file,
                    "photo_file": photo_path,
                    "document_file": doc_path
                })
                log_interaction(text, bubbles)
                print(f"[ANTIGRAVITY ASYNC COMPLETE in {res.get('duration', 0):.1f}s]")
            else:
                err_msg = res.get("error", "Error desconocido")
                print(f"[ANTIGRAVITY ASYNC ERROR] {err_msg}")
                self.send_message(chat_id, "Antigravity tardó más de lo esperado. Si quieres lo intentamos de nuevo.")
        except Exception as e:
            stop_event.set()
            print(f"[ANTIGRAVITY EXCEPTION] {e}")
            self.send_message(chat_id, "Hubo un detalle de conexión con Antigravity. Lo reviso enseguida.")

    def handle_incoming_message(self, message: dict):
        chat_id = message.get("chat", {}).get("id")
        if chat_id != ALLOWED_CHAT_ID:
            print(f"[SECURITY] Intento de acceso no autorizado desde chat_id: {chat_id}")
            return

        text = message.get("text", "")
        document = message.get("document")
        location = message.get("location")
        voice = message.get("voice")
        audio = message.get("audio")
        is_from_voice = False

        # 0. Si el usuario envió una nota de voz
        if voice or audio:
            voice_obj = voice or audio
            file_id = voice_obj.get("file_id")
            print(f"[VOICE/AUDIO RECEIVED] file_id={file_id}")
            self.send_action(chat_id, "record_voice")
            temp_voice_in = f"/tmp/tg_voice_in_{int(time.time())}_{file_id[:8]}.ogg"
            if self.download_telegram_file(file_id, temp_voice_in):
                transcribed = transcribe_telegram_voice(temp_voice_in)
                if os.path.exists(temp_voice_in):
                    try:
                        os.remove(temp_voice_in)
                    except Exception:
                        pass
                if transcribed:
                    print(f"[VOICE TRANSCRIBED SUCCESS] '{transcribed}'")
                    text = transcribed
                    is_from_voice = True
                else:
                    self.send_message(chat_id, "Niño, te escuché medio cortado el audio. ¿Me lo mandas de nuevo o me escribes qué pasó?")
                    return
            else:
                self.send_message(chat_id, "No pude descargar tu nota de voz, corazón. Reinténtalo en un segundito.")
                return

        # Ubicación: no se procesa (privacidad)
        if location:
            self.send_message(chat_id, "No guardo ubicaciones. Escríbeme lo que necesitas.")
            return

        # 2. Si el usuario confirma explícitamente una tarea proactiva
        if text and len(self.pending_tasks) > 0:
            lower = text.lower().strip()
            confirmation_triggers = [
                "listo", "ya voy", "saliendo", "en camino", "comí", "comi",
                "ya comí", "ya comi", "entrené", "entrene", "ya entrene",
                "ya fui", "terminé", "termine", "ya terminé", "ya termine",
                "ya salí", "ya sali", "ya lo hice", "hecho listo"
            ]
            if lower in confirmation_triggers or any(lower.startswith(p) for p in ["ya terminé ", "ya termine ", "ya comí ", "ya entrene "]):
                for task_key in list(self.pending_tasks.keys()):
                    self.pending_tasks[task_key]["confirmed"] = True
                bubbles = [
                    "Listo, queda registrado."
                ]
                self.deliver_response_package(chat_id, {"bubbles": bubbles})
                return

        # 3. Si el usuario envió una foto / imagen
        photo = message.get("photo")
        if photo:
            largest_photo = photo[-1]
            file_id = largest_photo.get("file_id")
            caption = message.get("caption", "").strip()
            temp_photo_path = f"/tmp/tg_photo_{int(time.time())}_{file_id[:8]}.jpg"
            if self.download_telegram_file(file_id, temp_photo_path):
                print(f"[PHOTO RECEIVED & DOWNLOADED] {temp_photo_path}")
                prompt_text = f"{USER_NAME} te acaba de enviar una imagen (guardada en '{temp_photo_path}')."
                if caption:
                    prompt_text += f" Junto con la foto escribió: '{caption}'"
                prompt_text += " Examina la imagen o coméntala según lo que te pide."
                text = prompt_text

        # 4. Si el usuario envió un archivo PPTX / documento
        if document:
            file_name = document.get("file_name", "archivo_descargado")
            file_id = document.get("file_id")
            wait_msg = f"Recibí '{file_name}', niño. Pérame un cachito que lo paso por el Mac para dejártelo en PDF y armar el cuaderno al tiro."
            self.send_action(chat_id, "typing")
            self.send_message(chat_id, wait_msg)
            threading.Thread(
                target=self._process_document_async,
                args=(chat_id, file_id, file_name),
                daemon=True
            ).start()
            return

        # 4. Mensajes de texto normales: Delegación Completa a Antigravity
        if text:
            print(f"[MSG FROM USUARIO] {text}")
            # Enviar acción typing natural sin mensaje mecánico de espera
            self.send_action(chat_id, "typing")

            threading.Thread(
                target=self._process_with_antigravity_async,
                args=(chat_id, text, is_from_voice),
                daemon=True
            ).start()

    def _process_document_async(self, chat_id: int, file_id: str, file_name: str):
        try:
            study_dir = os.path.join(BASE_DIR, "universidad", "estudio")
            os.makedirs(study_dir, exist_ok=True)
            local_target = os.path.join(study_dir, file_name)

            if self.download_telegram_file(file_id, local_target):
                if file_name.lower().endswith((".pptx", ".ppt")):
                    try:
                        bundle = build_notebooklm_bundle(local_target, study_dir)
                        self.send_action(chat_id, "upload_document")
                        self.send_message(chat_id, f"Listo {USER_NAME}, quedó convertido a PDF de alta resolución. Aquí te lo envío:")
                        self.send_document(chat_id, bundle["pdf_path"])
                        self.send_message(chat_id, "📘 Y aquí tienes la Guía con el Prompt de Estudio:")
                        self.send_document(chat_id, bundle["notebook_md_path"], caption=f"Prompt de estudio para {CAREER}")
                    except Exception as err:
                        self.send_message(chat_id, f"Hubo un detalle al convertir: {err}")
                else:
                    self.send_message(chat_id, f"Archivo guardado en tu Mac: {local_target}")
            else:
                self.send_message(chat_id, "No pude descargar el archivo desde Telegram.")
        except Exception as e:
            print(f"[ASYNC DOC ERROR] {e}")

    def proactive_scheduler_loop(self):
        """Hilo proactivo inteligente con recordatorios de rutina, Google Calendar y Life OS."""
        print("[SCHEDULER] Iniciado hilo proactivo inteligente de rutina y Life OS.")
        while self.is_running:
            try:
                now = datetime.now()
                today = now.date()
                today_str = now.strftime("%Y-%m-%d")
                weekday = now.weekday() # 0 = Lunes, 4 = Viernes, 6 = Domingo

                # Rotación semanal de avatar
                if today != self.current_date:
                    self.current_date = today
                    self.pending_tasks.clear()

                # 0. Recordatorios Personalizados Guardados (revisión continua cada 30s)
                try:
                    custom_due = check_and_pop_custom_reminders(now)
                    for rem in custom_due:
                        self.deliver_response_package(ALLOWED_CHAT_ID, {
                            "bubbles": [f"🔔 **Recordatorio:** {rem.get('mensaje')}"]
                        })
                except Exception as cre:
                    print(f"[CUSTOM REMINDER ERROR] {cre}")

                # 0b. Pre-alerta de Google Calendar (60 min antes de una cita o evento)
                try:
                    cal_alert = get_calendar_pre_alert(now)
                    if cal_alert:
                        save_sent_alert(cal_alert["key"])
                        self.deliver_response_package(ALLOWED_CHAT_ID, {
                            "bubbles": [cal_alert["message"]]
                        })
                except Exception as cae:
                    print(f"[CALENDAR PRE-ALERT ERROR] {cae}")

                # 0c. Monitoreo de alta señal en Gmail (cada 10 min)
                if int(now.timestamp()) % 600 < 35:
                    try:
                        from scripts.gmail_high_signal_scanner import get_high_signal_gmail_alerts
                        gm_alerts = get_high_signal_gmail_alerts(15)
                        for a in gm_alerts:
                            alert_k = f"gmail_sig_{a['categoria']}_{a['asunto'][:25]}_{a.get('fecha', '')[:10]}"
                            if not has_alert_been_sent(alert_k):
                                save_sent_alert(alert_k)
                                self.deliver_response_package(ALLOWED_CHAT_ID, {
                                    "bubbles": [a["mensaje_bot"]]
                                })
                    except Exception as ge:
                        print(f"[GMAIL HIGH SIGNAL ERROR] {ge}")

                # 1. Briefing Matutino Completo (08:30 Lun-Vie / 09:30 Sáb-Dom)
                target_morning_h = 8 if weekday < 5 else 9
                target_morning_m = 30
                alert_key = f"morning_briefing_{today_str}"
                if in_time_window(now, target_morning_h, target_morning_m, 20) and not has_alert_been_sent(alert_key):
                    save_sent_alert(alert_key)
                    try:
                        bubbles = get_morning_briefing(now)
                        self.deliver_response_package(ALLOWED_CHAT_ID, {"bubbles": bubbles})
                    except Exception as me:
                        print(f"[MORNING BRIEFING ERROR] {me}")

                # 2. Sincronización Académica universidad (09:00 AM y 18:00 PM)
                for sync_h in [9, 18]:
                    sync_key = f"sync_academic_{sync_h}00_{today_str}"
                    if in_time_window(now, sync_h, 0, 15) and not has_alert_been_sent(sync_key):
                        save_sent_alert(sync_key)
                        try:
                            print(f"[AUTO-SYNC] Sincronizando Moodle y correos ({sync_h}:00)...")
                            run_academic_sync()
                        except Exception as se:
                            print(f"[AUTO-SYNC ERROR] {se}")

                # 3. Recordatorios diarios definidos en config/config.json
                for rem in DAILY_REMINDERS:
                    try:
                        h, m = (int(x) for x in rem["time"].split(":"))
                        if rem.get("weekdays_only") and weekday >= 5:
                            continue
                        alert_key = f"{rem.get('key', rem['time'])}_{today_str}"
                        if in_time_window(now, h, m, 15) and not has_alert_been_sent(alert_key):
                            save_sent_alert(alert_key)
                            self.deliver_response_package(ALLOWED_CHAT_ID, {"bubbles": [rem["message"]]})
                    except Exception as rerr:
                        print(f"[DAILY REMINDER ERROR] {rerr}")

                # 9. Bloque de Avance Académico / tareas (19:00 PM Diario)
                alert_key = f"estudio_{today_str}"
                if in_time_window(now, 19, 0, 25) and not has_alert_been_sent(alert_key):
                    save_sent_alert(alert_key)
                    try:
                        bubbles = get_study_focus_bubbles(now)
                        self.deliver_response_package(ALLOWED_CHAT_ID, {"bubbles": bubbles})
                    except Exception as te:
                        print(f"[TASK CHECK ERROR] {te}")

                # 10. Check-in Nocturno y Revisión del Día Siguiente (21:30 PM Diario)
                alert_key = f"evening_briefing_{today_str}"
                if in_time_window(now, 21, 30, 20) and not has_alert_been_sent(alert_key):
                    save_sent_alert(alert_key)
                    try:
                        bubbles = get_evening_briefing(now)
                        self.deliver_response_package(ALLOWED_CHAT_ID, {"bubbles": bubbles})
                    except Exception as ee:
                        print(f"[EVENING BRIEFING ERROR] {ee}")

                # 12. Auditoría Diaria Automatizada (23:00 PM Diario)
                alert_key = f"daily_audit_{today_str}"
                if in_time_window(now, 23, 0, 20) and not has_alert_been_sent(alert_key):
                    save_sent_alert(alert_key)
                    try:
                        print(f"[AUDITOR] Iniciando auditoría diaria automatizada de las 23:00 para {today_str}...")
                        audit_res = run_daily_audit(today_str)
                        if audit_res.get("success"):
                            pdf_p = audit_res["pdf_path"]
                            self.deliver_response_package(ALLOWED_CHAT_ID, {
                                "bubbles": [
                                    f"{USER_NAME}, son las 23:00. Acabo de auditar todos los chats y audios de nuestra jornada ({audit_res['total_interactions']} interacciones).",
                                    f"📊 **Veredicto:** {audit_res['veredicto']}\nAquí tienes el PDF con el detalle de si hice bien mi trabajo y las anomalías o mejoras detectadas.",
                                    "Revisa el informe con calma y dime si quieres que apliquemos alguna de las mejoras sugeridas 😉"
                                ],
                                "document_file": pdf_p
                            })
                    except Exception as ae:
                        print(f"[DAILY AUDIT ERROR] {ae}")

            except Exception as loop_err:
                print(f"[SCHEDULER LOOP EXCEPTION] {loop_err}")

            time.sleep(30)

    def moodle_keepalive_loop(self):
        """Mantiene viva la sesión de Moodle en Google Chrome enviando un ping cada 120s."""
        while self.is_running:
            try:
                from scripts.moodle_extractor import ping_moodle_keepalive
                ping_moodle_keepalive()
            except Exception:
                pass
            time.sleep(120)

    def run(self):
        print(f"[DAEMON] {ASSISTANT_NAME} Life OS conectada con Antigravity para chat_id: {ALLOWED_CHAT_ID}")
        scheduler_thread = threading.Thread(target=self.proactive_scheduler_loop, daemon=True)
        scheduler_thread.start()
        moodle_thread = threading.Thread(target=self.moodle_keepalive_loop, daemon=True)
        moodle_thread.start()

        while self.is_running:
            try:
                url = f"{BASE_URL}/getUpdates?offset={self.last_update_id}&timeout=25"
                res = requests.get(url, timeout=30).json()
                if res.get("ok"):
                    for update in res.get("result", []):
                        self.last_update_id = update["update_id"] + 1
                        msg = update.get("message") or update.get("edited_message")
                        if msg:
                            self.handle_incoming_message(msg)
                else:
                    time.sleep(3)
            except Exception as e:
                print(f"[POLL EXCEPTION] {e}")
                time.sleep(3)

if __name__ == "__main__":
    daemon = TelegramCoachDaemon()
    daemon.run()
