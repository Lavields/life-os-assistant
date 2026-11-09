"""
Configuración personal del asistente.

Los datos de la persona (nombre, correos, institución, recordatorios) viven en
config/config.json, que está ignorado por git. config/config.example.json
documenta el formato.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.getenv("LIFE_OS_CONFIG", os.path.join(BASE_DIR, "config", "config.json"))
_EXAMPLE_PATH = os.path.join(BASE_DIR, "config", "config.example.json")


def _load() -> dict:
    for path in (_CONFIG_PATH, _EXAMPLE_PATH):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


CONFIG = _load()

USER_NAME = CONFIG.get("user_name", "Usuario")
ASSISTANT_NAME = CONFIG.get("assistant_name", "Asistente")
INSTITUTION = CONFIG.get("institution", "la universidad")
CAREER = CONFIG.get("career", "mi carrera")
TIMEZONE_LABEL = CONFIG.get("timezone_label", "Chile")
PERSONA = CONFIG.get("persona", "")
INSTITUTIONAL_EMAIL = CONFIG.get("emails", {}).get("institutional", "")
PERSONAL_EMAIL = CONFIG.get("emails", {}).get("personal", "")
INSTITUTIONAL_MAIL_ACCOUNT = CONFIG.get("mail_accounts", {}).get("institutional", "Exchange")
PERSONAL_MAIL_ACCOUNT = CONFIG.get("mail_accounts", {}).get("personal", "Google")
MOODLE_URL = CONFIG.get("moodle_url", "")
DAILY_REMINDERS = CONFIG.get("daily_reminders", [])
INSTITUTION_DOMAIN = CONFIG.get("institution_domain", "")
