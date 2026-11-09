#!/usr/bin/env python3
"""
Motor de Voz Dinámico Multi-Nacionalidad en la Nube (Fish Audio)
- Voces seleccionadas por el usuario:
  • Perú: PE-2 (Limeña Natural) - 4f14af9dd525408f884f532ca907e3fe
  • Chile: CL-2 (Chilena Natural) - dfd23dbaf3a04dd2b358d3ab44ecf15f
  • Chile Pro: CL-5 (Veducha Chile) - 30f0d0a109a44f87a3a896b12aa0af41
  • Argentina: AR-5 (Profesora Argentina) - 55589185654d4d5abc1035280611fb65
  • Colombia: CO-2 (Colombiana Conversacional) - 84a980d0ef3d4f8ea185951bd920afbe
- Cambio dinámico de acento por comando en Telegram.
- Ejecución 100% en la nube vía Fish Audio con el modelo gratuito s2.1-pro-free.
"""

import os
import json
import requests
import subprocess
import tempfile
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE_DIR, ".env")
PREF_FILE = os.path.join(BASE_DIR, "memoria", "preferencias_asistente.json")

if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

FISH_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
FISH_API_KEY_BACKUP = os.getenv("FISH_AUDIO_API_KEY_BACKUP", "")
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"

def load_voice_prefs():
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "voz_activa": "peruana",
        "modelo_id": "4f14af9dd525408f884f532ca907e3fe",
        "nombre_voz": "PE-2: Limeña Natural"
    }

def save_voice_prefs(prefs):
    with open(PREF_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

def set_active_voice(target: str) -> dict:
    """
    Cambia la voz activa según nacionalidad o código:
    'cl-f1', 'cl-f2', 'cl-f3', 'cl-f4', 'cl-f5', 'cl-f', 'cl-a', 'cl-b', 'cl-c', 'cl-d', 'cl-e', 'cl-g', etc.
    """
    prefs = load_voice_prefs()
    catalog = prefs.get("catalogo", {})
    t = target.lower().strip()

    chosen_key = None
    if any(k in t for k in ["cl-f1", "clf1", "f1"]):
        chosen_key = "chilena_f1"
    elif any(k in t for k in ["cl-f2", "clf2", "f2"]):
        chosen_key = "chilena_f2"
    elif any(k in t for k in ["cl-f3", "clf3", "f3"]):
        chosen_key = "chilena_f3"
    elif any(k in t for k in ["cl-f4", "clf4", "f4"]):
        chosen_key = "chilena_f4"
    elif any(k in t for k in ["cl-f5", "clf5", "f5"]):
        chosen_key = "chilena_f5"
    elif any(k in t for k in ["cl-f", "clf", "opcion f", "opción f", "soft"]):
        chosen_key = "chilena_f1" # Default F a la versión con énfasis F1
    elif any(k in t for k in ["cl-a", "cla", "opcion a", "opción a", "casual"]):
        chosen_key = "chilena_casual"
    elif any(k in t for k in ["cl-b", "clb", "opcion b", "opción b", "conversacional chilena"]):
        chosen_key = "chilena_conversacional"
    elif any(k in t for k in ["cl-c", "clc", "opcion c", "opción c", "expresiva"]):
        chosen_key = "chilena_expresiva"
    elif any(k in t for k in ["cl-d", "cld", "opcion d", "opción d", "cozy"]):
        chosen_key = "chilena_cozy"
    elif any(k in t for k in ["cl-e", "cle", "opcion e", "opción e", "animada"]):
        chosen_key = "chilena_animada"
    elif any(k in t for k in ["cl-g", "clg", "opcion g", "opción g", "podcast", "moderna"]):
        chosen_key = "chilena_podcast"
    elif any(k in t for k in ["chile", "chilena", "santiago"]):
        chosen_key = "chilena_f1"
    elif any(k in t for k in ["peru", "peruana", "limeña", "pe-2", "pe2"]):
        chosen_key = "peruana"
    elif any(k in t for k in ["argentina", "argentino", "ar-5", "ar5", "porteña"]):
        chosen_key = "argentina"
    elif any(k in t for k in ["colombia", "colombiana", "co-2", "co2", "paisa"]):
        chosen_key = "colombiana"

    if chosen_key and chosen_key in catalog:
        entry = catalog[chosen_key]
        prefs["voz_activa"] = chosen_key
        prefs["modelo_id"] = entry["modelo_id"]
        prefs["nombre_voz"] = entry["nombre"]
        save_voice_prefs(prefs)
        return {
            "success": True,
            "key": chosen_key,
            "nombre": entry["nombre"],
            "saludo": entry["saludo"],
            "modelo_id": entry["modelo_id"]
        }
    return {
        "success": False,
        "current": prefs.get("nombre_voz")
    }

EMOTION_CONFIGS = {
    "neutral": {
        "description": "Modo Neutral-Práctico (Nivel 3 Equilibrado): Coordinación, horarios, datos médicos y tareas. Conversación normal: ritmo real, con variación de tono.",
        "speed": 1.0,
        "temperature": 0.68,
        "volume": 0.0,
        "loudnorm_i": -17.5,
        "loudnorm_tp": -1.5,
        "loudnorm_lra": 8.0,
        "filter_chain": "highpass=f=75,loudnorm=I=-17.5:TP=-1.5:LRA=8.0"
    },
    "warm": {
        "description": "Modo Cálido-Contenedor: Apoyo en estrés, desahogo, contención o cierre nocturno con cadencia reposada.",
        "speed": 0.94,
        "temperature": 0.52,
        "volume": -0.5,
        "loudnorm_i": -19.5,
        "loudnorm_tp": -2.0,
        "loudnorm_lra": 4.5,
        "filter_chain": "highpass=f=80,equalizer=f=220:t=q:w=1.2:g=1.0,equalizer=f=3200:t=q:w=1.0:g=0.5,equalizer=f=6500:t=q:w=1.8:g=-1.2,lowpass=f=14000,loudnorm=I=-19.5:TP=-2.0:LRA=4.5"
    },
    "playful": {
        "description": "Modo Juguetón-Chispeante: Bromas ligeras, pausas de café/dulces y humor espontáneo sin sobresaltos.",
        "speed": 0.98,
        "temperature": 0.58,
        "volume": 0.3,
        "loudnorm_i": -16.8,
        "loudnorm_tp": -1.2,
        "loudnorm_lra": 5.2,
        "filter_chain": "highpass=f=75,equalizer=f=3200:t=q:w=1.0:g=0.8,loudnorm=I=-16.8:TP=-1.2:LRA=5.2"
    },
    "euphoric": {
        "description": "Modo Euforia / Celebración: Logros de entrenamiento, aprobación de asignaturas y festejo controlado.",
        "speed": 1.00,
        "temperature": 0.62,
        "volume": 1.0,
        "loudnorm_i": -15.0,
        "loudnorm_tp": -1.0,
        "loudnorm_lra": 6.0,
        "filter_chain": "highpass=f=80,alimiter=limit=-1.0dB:attack=5:release=60,loudnorm=I=-15.0:TP=-1.0:LRA=6.0"
    },
    "whisper": {
        "description": "Modo Susurro / Intimidad: Voz bajita, confesiones, complicidad cercana sin ruido de piso.",
        "speed": 0.90,
        "temperature": 0.50,
        "volume": -1.5,
        "loudnorm_i": -23.0,
        "loudnorm_tp": -4.0,
        "loudnorm_lra": 4.0,
        "filter_chain": "highpass=f=70,lowpass=f=12000,equalizer=f=220:t=q:w=1.0:g=2.0,loudnorm=I=-23.0:TP=-4.0:LRA=4.0"
    }
}

def detect_emotion_mode(text: str) -> str:
    """Detecta heurísticamente el modo emocional según el contenido y vocabulario."""
    lower = text.lower()
    
    # 1. Susurro / Intimidad
    if any(k in lower for k in ["secreto", "voz bajita", "susurro", "al oído", "al oido", "en bajito", "shhh", "no le digas a nadie"]):
        return "whisper"
        
    # 2. Euforia / Celebración
    if any(k in lower for k in ["siii", "me muero de la emoción", "felicidades", "lo lograste", "ganamos", "demasiado seco", "qué seco", "que seco", "golazo", "épico", "epico"]):
        return "euphoric"
        
    # 3. Cálido / Contenedor
    if any(k in lower for k in ["respira", "tranquilo", "tranqui la mente", "abrazo grande", "descansa", "estoy contigo", "calma", "no te me agobies", "paso a pasito", "baja la guardia", "te acompaño", "buenas noches"]):
        return "warm"
        
    # 4. Juguetón / Chispeante
    if any(k in lower for k in ["jajaja", "jeje", "pffff", "tontera", "meme", "chiste", "broma", "partida", "silla gamer", "tortita", "rollito de canela", "cafecito", "antojo", "pastel"]):
        return "playful"
        
    # 5. Default por Principio de Neutralidad Situacional
    return "neutral"

THINKING_FILLERS = ("mmm", "eee")
FILLER_PAUSE = "..."  # Pausa después de la muletilla

def add_thinking_fillers(text: str) -> str:
    """Agrega una pausa de "pensar" cada dos oraciones, sin tocar textos cortos ni la primera oración."""
    import re
    import zlib
    if len(text.split()) < 12 or re.search(r'\b(mmm+|eee+|ehh+)\b', text, re.IGNORECASE):
        return text

    sentences = re.split(r'(?<=[.?])\s+', text)
    # La semilla sale del texto: el mismo mensaje siempre suena igual
    filler_index = zlib.crc32(text.encode("utf-8")) % len(THINKING_FILLERS)
    for i in range(1, len(sentences), 2):
        filler = THINKING_FILLERS[filler_index % len(THINKING_FILLERS)]
        filler_index += 1
        sentence = sentences[i]
        if sentence:
            lowered = sentence[0].lower() + sentence[1:] if not sentence[:4].isupper() else sentence
            sentences[i] = f"{filler.capitalize()}{FILLER_PAUSE} {lowered}"
    return " ".join(sentences)

def format_text_for_natural_voice(text: str, emotion_mode: str = "neutral") -> str:
    """Limpia el texto para que se lea como habla real, sin añadir pausas ni muletillas artificiales."""
    import re
    t = text

    # 1. Sacar lo que no se pronuncia: markdown, emojis y símbolos
    t = re.sub(r'[*_#`~]', '', t)
    t = re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]', '', t)

    # 2. Risas cortas, sin actuarlas
    t = re.sub(r'\b(?:ja){2,}\b', 'jaja', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:je){2,}\b', 'jeje', t, flags=re.IGNORECASE)

    # 3. Mayúsculas de énfasis a minúsculas; las siglas se conservan
    siglas = {"LMS", "PDF"}
    t = re.sub(r'\b[A-ZÁÉÍÓÚÑ]{4,}\b', lambda m: m.group(0) if m.group(0) in siglas else m.group(0).lower(), t)

    # 4. Puntuación según modo: la elipsis y la exclamación suenan a locución actuada
    if emotion_mode == "whisper":
        t = t.replace("¡", "").replace("!", "...").replace("?", "...")
        t = re.sub(r'\.{4,}', '...', t)
    else:
        t = re.sub(r'\s*(?:\.{2,}|…)\s*', ', ', t)
        if emotion_mode in ["neutral", "warm"]:
            t = t.replace("¡", "").replace("!", ".")

    # 5. Espacios
    t = re.sub(r'\s+([,.;:?])', r'\1', t)
    t = re.sub(r',\s*([.?])', r'\1', t)
    t = re.sub(r'\s{2,}', ' ', t).strip()

    return t

def text_to_telegram_voice(text: str, model_id_override: str = None, emotion_mode: str = None) -> str:
    """
    Sintetiza texto a OGG Opus nativo de Telegram / WhatsApp con física acústica situada:
    - Normalización EBU R128 adaptativa por estado emocional.
    - Curva EQ de cercanía / presencia vocal.
    - Prevención de clipeo inter-sample mediante limitador lookahead.
    """
    prefs = load_voice_prefs()
    model_id = model_id_override or prefs.get("modelo_id", "8c367b71c42a4858bc2dd688ebe1cabc")
    
    mode = emotion_mode or detect_emotion_mode(text)
    config = EMOTION_CONFIGS.get(mode, EMOTION_CONFIGS["neutral"])
    
    smooth_text = format_text_for_natural_voice(text, emotion_mode=mode)
    if mode in ("neutral", "playful"):
        smooth_text = add_thinking_fillers(smooth_text)

    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free"
    }
    
    # normalize_loudness en False permite que el modelo respire de forma orgánica;
    # nuestro DSP con FFmpeg en la máquina local se encarga de la precisión en LUFS y True Peak.
    payload = {
        "text": smooth_text,
        "reference_id": model_id,
        "format": "mp3",
        "temperature": config["temperature"],
        "prosody": {
            "speed": config["speed"],
            "volume": config["volume"],
            "normalize_loudness": False
        }
    }

    temp_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    ogg_file = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False).name

    try:
        r = requests.post("https://api.fish.audio/v1/tts", json=payload, headers=headers, timeout=180)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(temp_mp3, "wb") as f:
                f.write(r.content)
        elif FISH_API_KEY_BACKUP:
            print(f"[FISH PRIMARY FAILED: {r.status_code}] Probando clave Fish de respaldo...")
            backup_headers = {
                "Authorization": f"Bearer {FISH_API_KEY_BACKUP}",
                "Content-Type": "application/json",
                "model": "s2.1-pro-free"
            }
            r_back = requests.post("https://api.fish.audio/v1/tts", json=payload, headers=backup_headers, timeout=180)
            if r_back.status_code == 200 and len(r_back.content) > 1000:
                with open(temp_mp3, "wb") as f:
                    f.write(r_back.content)
            else:
                print(f"[FISH BACKUP FAILED: {r_back.status_code}] Fallback a síntesis local...")
                cmd = ["say", "-v", "Paulina", "--file-format=WAVE", "-o", temp_mp3, text]
                subprocess.run(cmd, check=True)
        else:
            print(f"[FISH ERROR] Status: {r.status_code}, fallback a síntesis local...")
            cmd = ["say", "-v", "Paulina", "--file-format=WAVE", "-o", temp_mp3, text]
            subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"[VOICE EXCEPTION] {e}, fallback a clave de respaldo o local...")
        try:
            if FISH_API_KEY_BACKUP:
                backup_headers = {
                    "Authorization": f"Bearer {FISH_API_KEY_BACKUP}",
                    "Content-Type": "application/json",
                    "model": "s2.1-pro-free"
                }
                r_back = requests.post("https://api.fish.audio/v1/tts", json=payload, headers=backup_headers, timeout=180)
                if r_back.status_code == 200 and len(r_back.content) > 1000:
                    with open(temp_mp3, "wb") as f:
                        f.write(r_back.content)
                else:
                    cmd = ["say", "-v", "Paulina", "--file-format=WAVE", "-o", temp_mp3, text]
                    subprocess.run(cmd, check=True)
            else:
                cmd = ["say", "-v", "Paulina", "--file-format=WAVE", "-o", temp_mp3, text]
                subprocess.run(cmd, check=True)
        except Exception:
            cmd = ["say", "-v", "Paulina", "--file-format=WAVE", "-o", temp_mp3, text]
            subprocess.run(cmd, check=True)

    # Conversión a OGG Opus con cadena DSP acústica adaptada a WhatsApp Physics
    ffmpeg_bin = FFMPEG_PATH if os.path.exists(FFMPEG_PATH) else "ffmpeg"
    dsp_chain = config["filter_chain"]
    
    cmd = [
        ffmpeg_bin, "-y", "-i", temp_mp3,
        "-af", dsp_chain,
        "-c:a", "libopus",
        "-b:a", "48k",
        "-vbr", "on",
        "-ar", "48000",
        "-ac", "1",
        "-compression_level", "10",
        ogg_file
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    if os.path.exists(temp_mp3):
        os.remove(temp_mp3)

    return ogg_file

def transcribe_telegram_voice(audio_path: str) -> str:
    """
    Transcribe notas de voz y audios de Telegram a texto en alta velocidad (<1s)
    utilizando el modelo whisper-large-v3-turbo en Groq.
    """
    if not os.path.exists(audio_path):
        return ""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return ""
    try:
        filename = os.path.basename(audio_path)
        mime = "audio/ogg" if filename.lower().endswith((".ogg", ".oga", ".opus")) else "audio/mpeg"
        with open(audio_path, "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {groq_key}"},
                files={"file": (filename, f, mime)},
                data={"model": "whisper-large-v3-turbo", "language": "es"},
                timeout=15
            )
        if res.status_code == 200:
            return res.json().get("text", "").strip()
        else:
            print(f"[TRANSCRIPTION ERROR] Status {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[TRANSCRIPTION EXCEPTION] {e}")
    return ""

if __name__ == "__main__":
    v = set_active_voice("chilena")
    print("Switch voice test:", v)
    path = text_to_telegram_voice(f"Hola {USER_NAME}, probando voz activa.")
    print("Audio generado:", path, os.path.getsize(path))
