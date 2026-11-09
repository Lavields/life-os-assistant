#!/usr/bin/env python3
"""
Carga de secretos y protección de logs.
- load_env(): lee el .env de la raíz del proyecto hacia os.environ.
- install_log_redaction(): impide que claves o tokens lleguen a daemon.log.
Los secretos viven SOLO en .env; nunca como valor por defecto en el código.
"""

import os
import re
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE_DIR, ".env")
TRASH_DIR = os.path.expanduser("~/.Trash")

_SECRET_PATTERNS = [
    re.compile(r"\d{8,10}:AA[A-Za-z0-9_-]{20,}"),      # Telegram
    re.compile(r"sk-fish-[A-Za-z0-9_-]+"),             # Fish Audio
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),               # Groq
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),             # Google / Gemini
    re.compile(r"AQ\.[A-Za-z0-9_.-]{20,}"),            # Google (claves con prefijo AQ.)
]


def load_env(path: str = ENV_FILE) -> None:
    """Carga KEY=VALUE desde .env. No falla si el archivo no existe."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def redact(text: str) -> str:
    """Reemplaza cualquier secreto reconocible por [OCULTO]."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[OCULTO]", text)
    return text


class _RedactingStream:
    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(redact(text) if isinstance(text, str) else text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_log_redaction() -> None:
    """Filtra stdout y stderr del proceso. Es idempotente."""
    if not isinstance(sys.stdout, _RedactingStream):
        sys.stdout = _RedactingStream(sys.stdout)
    if not isinstance(sys.stderr, _RedactingStream):
        sys.stderr = _RedactingStream(sys.stderr)


def is_safe_outgoing_file(path) -> bool:
    """Solo salen por Telegram archivos del proyecto o temporales, nunca secretos ni logs."""
    if not path or not isinstance(path, str):
        return False
    real = os.path.realpath(path)
    allowed_roots = (os.path.realpath(BASE_DIR) + os.sep, "/private/tmp/", "/private/var/folders/")
    if not real.startswith(allowed_roots):
        return False
    name = os.path.basename(real).lower()
    blocked_suffixes = (".log", ".plist", ".pem", ".key", ".py", ".bak", ".bak2", ".bak3")
    return not (name.startswith(".env") or name.endswith(blocked_suffixes))


def release_delivered_document(path) -> str:
    """
    Tras enviar un PDF por Telegram, no deja copia si ya existe el contenido en texto.
    - PDF temporal: se elimina.
    - PDF del proyecto con .md o .html al lado: va a la Papelera (recuperable).
    - Cualquier otro archivo, como material de la U o exámenes: no se toca.
    Devuelve "removed", "trashed" o "kept".
    """
    if not path or not isinstance(path, str) or not path.lower().endswith(".pdf") or not os.path.isfile(path):
        return "kept"
    real = os.path.realpath(path)
    if real.startswith(("/private/tmp/", "/private/var/folders/")):
        os.remove(real)
        return "removed"
    if real.startswith(os.path.realpath(BASE_DIR) + os.sep):
        stem = os.path.splitext(real)[0]
        if any(os.path.exists(stem + ext) and os.path.getsize(stem + ext) > 0 for ext in (".md", ".html")):
            name = os.path.basename(real)
            target = os.path.join(TRASH_DIR, name)
            if os.path.exists(target):
                target = os.path.join(TRASH_DIR, f"{os.path.splitext(name)[0]}_{int(time.time())}.pdf")
            shutil.move(real, target)
            return "trashed"
    return "kept"
