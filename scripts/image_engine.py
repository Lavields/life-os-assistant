#!/usr/bin/env python3
"""
Motor de Generación Visual de Tarjetas Informativas (asistente)
Genera imágenes nítidas de alta resolución (estilo Dark Mode iOS) para Telegram:
- Horario diario (config/config.json -> "schedule")
- Rutina de entrenamiento (config/config.json -> "workout")
"""

import os
import tempfile
import json
from PIL import Image, ImageDraw, ImageFont
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME, CONFIG
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME, CONFIG

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"

def get_font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def create_base_canvas(width: int, height: int, title: str, subtitle: str, tag: str = "MI_COUCH OS"):
    img = Image.new("RGB", (width, height), color=(18, 20, 29)) # Fondo Dark Slate #12141D
    draw = ImageDraw.Draw(img)

    # Borde exterior suave
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=24, outline=(40, 44, 60), width=2)

    # Tag superior
    font_tag = get_font(18)
    draw.rounded_rectangle([40, 35, 180, 65], radius=8, fill=(35, 45, 75))
    draw.text((55, 41), tag, font=font_tag, fill=(130, 180, 255))

    # Título Principal
    font_title = get_font(34)
    draw.text((40, 80), title, font=font_title, fill=(255, 255, 255))

    # Subtítulo
    font_sub = get_font(20)
    draw.text((40, 125), subtitle, font=font_sub, fill=(160, 168, 190))

    # Línea divisoria
    draw.line([(40, 160), (width - 40, 160)], fill=(45, 50, 70), width=2)

    return img, draw

def generate_schedule_card() -> str:
    """Genera la tarjeta visual del horario diario."""
    width, height = 850, 1050
    img, draw = create_base_canvas(width, height, "Horario del día", "Bloques definidos en tu configuración")

    palette = [(100, 120, 140), (80, 180, 140), (240, 160, 80), (100, 180, 255), (150, 120, 200), (220, 100, 100), (80, 220, 160)]
    events = [(b["time"], b["title"], b.get("detail", ""), palette[n % len(palette)])
              for n, b in enumerate(CONFIG.get("schedule", []))]

    y = 185
    font_time = get_font(20)
    font_head = get_font(22)
    font_desc = get_font(18)

    for time_str, headline, desc, color in events:
        # Píldora de hora
        draw.rounded_rectangle([40, y, 220, y + 42], radius=10, fill=(28, 32, 46), outline=color, width=2)
        draw.text((50, y + 10), time_str, font=font_time, fill=(230, 235, 245))

        # Contenido
        draw.text((245, y + 2), headline, font=font_head, fill=(255, 255, 255))
        draw.text((245, y + 30), desc, font=font_desc, fill=(160, 170, 190))

        y += 82

    out_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    img.save(out_path)
    return out_path

def generate_workout_card() -> str:
    """Genera la tarjeta visual del entrenamiento nocturno de 20 min."""
    width, height = 850, 850
    img, draw = create_base_canvas(width, height, "Rutina de entrenamiento", "Ejercicios definidos en tu configuración", "FUERZA & METABOLISMO")

    palette = [(100, 180, 255), (80, 220, 160), (240, 180, 90), (240, 120, 100), (180, 140, 240)]
    exercises = [(f"{n + 1:02d}", e["name"], e.get("sets", ""), e.get("notes", ""), palette[n % len(palette)])
                 for n, e in enumerate(CONFIG.get("workout", []))]

    y = 185
    for num, name, sets, notes, color in exercises:
        draw.rounded_rectangle([40, y, 100, y + 60], radius=12, fill=color)
        draw.text((55, y + 15), num, font=get_font(26), fill=(15, 18, 25))

        draw.text((120, y), name, font=get_font(22), fill=(255, 255, 255))
        draw.text((120, y + 28), sets, font=get_font(18), fill=(220, 230, 245))
        draw.text((120, y + 54), notes, font=get_font(16), fill=(160, 170, 190))

        y += 115

    out_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    img.save(out_path)
    return out_path

if __name__ == "__main__":
    p1 = generate_schedule_card()
    p3 = generate_workout_card()
    print("Cards generated successfully:")
    print("Schedule:", p1)
    print("Workout:", p3)
